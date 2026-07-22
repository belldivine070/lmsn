import logging
from celery import shared_task
from django.apps import apps
from django.utils import timezone
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)



@shared_task(bind=True, max_retries=3)
def send_single_email_task(self, recipient, subject, body, from_email, post_id, is_last=False):
    """
    Sends an individual email, creates a tracking BroadcastLog, and updates the main post status.
    If it fails, it retries 3 times with a 30-second delay.
    """
    BroadcastLog = apps.get_model('core', 'BroadcastLog')
    NewsPost = apps.get_model('core', 'NewsPost')
    
    recipient_email = recipient.strip()
    log_status = 'Sent'
    
    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient_email],
        )
        msg.content_subtype = "html"
        msg.send(fail_silently=False)
        return f"Successfully sent to {recipient_email}"
        
    except Exception as exc:
        log_status = 'Failed'
        logger.error(f"Error sending to {recipient_email}: {str(exc)}")
        
        # If we have exhausted our retries, log the final failure state and do not raise again
        if self.request.retries >= self.max_retries:
            BroadcastLog.objects.create(
                news_post_id=post_id,
                recipient_email=recipient_email,
                status=log_status
            )
            return f"Permanently failed sending to {recipient_email}"
            
        raise self.retry(exc=exc, countdown=30)
        
    finally:
        # Only log successful dispatches or definitive failures to avoid duplicate logs during retries
        if log_status == 'Sent' or self.request.retries >= self.max_retries:
            BroadcastLog.objects.create(
                news_post_id=post_id,
                recipient_email=recipient_email,
                status=log_status
            )
            
        # Cleanly close out the entire NewsPost lifecycle when the final worker finishes
        if is_last:
            NewsPost.objects.filter(id=post_id).update(
                status='sent',
                last_sent_at=timezone.now() if hasattr(NewsPost, 'last_sent_at') else timezone.now()
            )
            
            

@shared_task
def send_broadcast_task(post_id, recipient_list, from_email=None, subject=None):
    """
    Master Task: Spawns tracked sub-tasks for every recipient.
    Ensures empty target lists elegantly fall back to safe states.
    """
    NewsPost = apps.get_model('core', 'NewsPost')
    AppVariable = apps.get_model('core', 'AppVariable') # or your specific app label
    
    try:
        post = NewsPost.objects.get(id=post_id)
    except NewsPost.DoesNotExist:
        logger.error(f"NewsPost with ID {post_id} not found.")
        return "Post not found"
    
    email_subject = subject or post.subject or post.title
    
    # Resolve the sender email sequentially: 
    # Provided parameter -> Model column value -> AppVariable database setting fallback
    sender = from_email or post.sender_email or AppVariable.get_setting('official_email', 'noreply@bgtech.com')
    
    # Transition status out of 'draft' or 'scheduled'
    post.status = 'sending'
    post.save(update_fields=['status'])

    total_recipients = len(recipient_list)
    if total_recipients == 0:
        post.status = 'failed'
        post.save(update_fields=['status'])
        return "Broadcast canceled: Recipient list was empty."
    
    for index, recipient in enumerate(recipient_list):
        is_last_item = (index == total_recipients - 1)
        send_single_email_task.delay(
            recipient=recipient,
            subject=email_subject,
            body=post.content,
            from_email=sender,
            post_id=post.id,
            is_last=is_last_item
        )
    
    return f"Queued {total_recipients} individual email tasks."


@shared_task
def check_scheduled_broadcasts():
    """
    Celery Beat task to check for scheduled posts that are due to be sent.
    """
    NewsPost = apps.get_model('core', 'NewsPost')
    now = timezone.now()
    
    pending_posts = NewsPost.objects.filter(
        status__in=['draft', 'scheduled'],
        scheduled_time__lte=now
    )
    
    for post in pending_posts:
        recipients = post.gather_emails()
        if recipients:
            send_broadcast_task.delay(
                post_id=post.id,
                recipient_list=recipients,
                from_email=post.sender_email
            )
        else:
            logger.warning(f"Post {post.id} has no recipients in target audience.")
            post.status = 'failed'
            post.save(update_fields=['status'])          
            
