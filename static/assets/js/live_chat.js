document.addEventListener('DOMContentLoaded', function () {

    const chatWidget = document.getElementById('jumiaChatWidget');
    const chatLauncher = document.getElementById('chatBubbleLauncher');
    const closeBtn = document.getElementById('closeChatWidget');

    const chatCanvas = document.getElementById('chatLogsCanvas');
    const messageInput = document.getElementById('chatInputMessageField');
    const sendBtn = document.getElementById('triggerPushMessageBtn');

    const uploadBtn = document.getElementById('triggerUploadBtn');
    const fileInput = document.getElementById('chatAttachmentInput');

    const previewTrack = document.getElementById('mediaPreviewTrack');
    const previewContainer = document.getElementById('previewImagesContainer');

    let selectedFiles = [];

    const csrfToken =
        document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

    /*
    |--------------------------------------------------------------------------
    | Open / Close Core Widget Layout
    |--------------------------------------------------------------------------
    */
    chatLauncher.addEventListener('click', () => {
        chatWidget.style.display = 'flex';
        chatWidget.style.flexDirection = 'column';
        loadHistory();
    });

    closeBtn.addEventListener('click', () => {
        chatWidget.style.display = 'none';
    });

    /*
    |--------------------------------------------------------------------------
    | Upload Handling & Media Previews
    |--------------------------------------------------------------------------
    */
    uploadBtn.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', function () {
        selectedFiles = [...this.files];
        previewContainer.innerHTML = '';

        if (!selectedFiles.length) {
            previewTrack.style.display = 'none';
            return;
        }

        previewTrack.style.display = 'block';

        selectedFiles.forEach((file, index) => {
            const reader = new FileReader();
            reader.onload = function (e) {
                const wrapper = document.createElement('div');
                wrapper.className = 'position-relative';
                wrapper.innerHTML = `
                    <img src="${e.target.result}" style="width:60px; height:60px; object-fit:cover; border-radius:8px;">
                    <button type="button" class="btn btn-danger btn-sm position-absolute top-0 end-0" data-index="${index}" style="width:20px; height:20px; padding:0; font-size:10px;">×</button>
                `;
                previewContainer.appendChild(wrapper);

                wrapper.querySelector('button').addEventListener('click', () => {
                    selectedFiles.splice(index, 1);
                    wrapper.remove();
                    if (!selectedFiles.length) {
                        previewTrack.style.display = 'none';
                    }
                });
            };
            reader.readAsDataURL(file);
        });
    });

    /*
    |--------------------------------------------------------------------------
    | Fetch Historical Threads
    |--------------------------------------------------------------------------
    */
    async function loadHistory() {
        try {
            const response = await fetch('/core/support/chat/', {
                method: 'GET',
                credentials: 'same-origin'
            });
            const data = await response.json();
            if (!data.success) return;

            chatCanvas.innerHTML = '';
            data.history.forEach(msg => appendMessage(msg));
            scrollBottom();
        } catch (err) {
            console.error('History migration failure:', err);
        }
    }

    /*
    |--------------------------------------------------------------------------
    | Optimistic Message Processing System
    |--------------------------------------------------------------------------
    */
    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message && !selectedFiles.length) return;

        // Formulate modern system context parameters for optimistic render runtime
        const timestamp = new Date();
        const formattedTime = String(timestamp.getHours()).padStart(2, '0') + ':' + String(timestamp.getMinutes()).padStart(2, '0');
        
        // Map local binary image allocations out of file arrays instantly to secure seamless UI feedback
        const localOptimisticImageUrls = selectedFiles.map(file => URL.createObjectURL(file));

        const optimisticUserPayload = {
            is_admin: false,
            sender: 'You',
            text: message,
            time: formattedTime,
            image_urls: localOptimisticImageUrls
        };

        // STEP 1: Render localized user data fields instantly to interface
        appendMessage(optimisticUserPayload);
        scrollBottom();

        // STEP 2: Render automated visual system tracking element indicating engine execution
        const typingIndicatorElement = appendTypingIndicator();
        scrollBottom();

        // STEP 3: Package native multi-part data payload for transport matrix redirection
        const formData = new FormData();
        formData.append('message', message);
        selectedFiles.forEach(file => formData.append('images', file));

        // Lock form components globally to block duplicate thread races
        sendBtn.disabled = true;
        messageInput.disabled = true;
        uploadBtn.style.pointerEvents = 'none';

        // Flush localized layout parameters instantly to prevent input blocking delays
        messageInput.value = '';
        fileInput.value = '';
        selectedFiles = [];
        previewContainer.innerHTML = '';
        previewTrack.style.display = 'none';

        try {
            const response = await fetch('/core/support/chat/', {
                method: 'POST',
                body: formData,
                headers: { 'X-CSRFToken': csrfToken },
                credentials: 'same-origin'
            });

            const data = await response.json();
            
            // Remove the typing placeholder safely before managing endpoint conditions
            typingIndicatorElement.remove();

            if (!data.success) {
                alert(data.message || 'Message delivery failed.');
                return;
            }

            // Optional: If you want to update the optimistic element with explicit DB IDs or clean references, handle here.
            if (data.ai_response) {
                appendMessage(data.ai_response);
                scrollBottom();
            }

        } catch (err) {
            console.error('Network transport pipeline exception:', err);
            typingIndicatorElement.remove();
        } finally {
            // Restore complete interaction control mechanisms securely
            sendBtn.disabled = false;
            messageInput.disabled = false;
            uploadBtn.style.pointerEvents = 'auto';
            messageInput.focus();
            
            // Deallocate global URL references cleanly out of hardware memory stacks
            localOptimisticImageUrls.forEach(url => URL.revokeObjectURL(url));
        }
    }

    /*
    |--------------------------------------------------------------------------
    | Interface Event Bindings
    |--------------------------------------------------------------------------
    */
    messageInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener('click', sendMessage);

    /*
    |--------------------------------------------------------------------------
    | High Density Rendering Engines
    |--------------------------------------------------------------------------
    */
    function appendMessage(msg) {
        const wrapper = document.createElement('div');
        wrapper.className = msg.is_admin ? 'd-flex justify-content-start mb-3' : 'd-flex justify-content-end mb-3';

        let imagesHtml = '';
        if (msg.image_urls && msg.image_urls.length) {
            imagesHtml = `
                <div class="d-flex flex-wrap gap-2 mt-2">
                    ${msg.image_urls.map(img => `<img src="${img}" style="width:120px; border-radius:8px; cursor:pointer;">`).join('')}
                </div>
            `;
        }

        wrapper.innerHTML = `
            <div style="max-width:75%; padding:10px 12px; border-radius:14px; background:${msg.is_admin ? '#ffffff' : '#ff9900'}; color:${msg.is_admin ? '#212529' : '#fff'}; box-shadow:0 1px 3px rgba(0,0,0,.08);">
                <div style="font-size:12px; font-weight:600;">${msg.sender}</div>
                <div style="font-size:14px;">${escapeHtml(msg.text || '')}</div>
                ${imagesHtml}
                <div class="text-end mt-1" style="font-size:10px; opacity:.7;">${msg.time}</div>
            </div>
        `;

        chatCanvas.appendChild(wrapper);
    }

    function appendTypingIndicator() {
        const wrapper = document.createElement('div');
        wrapper.className = 'd-flex justify-content-start mb-3';
        wrapper.id = 'aiTypingIndicatorStub';
        
        wrapper.innerHTML = `
            <div style="max-width:75%; padding:12px 16px; border-radius:14px; background:#ffffff; color:#6c757d; box-shadow:0 1px 3px rgba(0,0,0,.08); font-size:13px; font-style:italic;" class="d-flex align-items-center gap-2">
                <span class="spinner-border spinner-border-sm text-warning" role="status"></span>
                AI Assistant is typing...
            </div>
        `;
        chatCanvas.appendChild(wrapper);
        return wrapper;
    }

    function scrollBottom() {
        chatCanvas.scrollTop = chatCanvas.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});