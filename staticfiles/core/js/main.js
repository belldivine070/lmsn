/* main.js */

/** * 1. Summernote Initialization
 * Checks if jQuery exists before running to avoid the crash seen in your console.
 */
function initSummernote() {
  if (window.jQuery && typeof $.fn.summernote !== "undefined") {
    $("#summernote").summernote({
      height: 700,
      focus: true,
    });
  }
}

/**
 * 2. Auto-Slug Generation
 * Automatically fills the slug as you type the title.
 */
function initSlugGenerator() {
  const titleField = document.querySelector('input[name="title"]');
  const slugField = document.querySelector('input[name="slug"]');

  if (titleField && slugField) {
    titleField.addEventListener("input", function () {
      const slugValue = titleField.value  
        .toLowerCase()
        .replace(/[^a-z0-9 -]/g, "") // remove invalid chars
        .replace(/\s+/g, "-") // collapse whitespace and replace by -
        .replace(/-+/g, "-"); // collapse dashes
      slugField.value = slugValue;
    });
  }
}

document.addEventListener("DOMContentLoaded", function () {
  // Run Initializers
  initSummernote();
  initSlugGenerator();


  /* ALERT DISMISSAL */
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach((alert) => {
    setTimeout(() => {
      if (alert) {
        // Use Bootstrap method if available, else remove manually
        const bsAlert = window.bootstrap
          ? bootstrap.Alert.getInstance(alert)
          : null;
        if (bsAlert) {
          bsAlert.close();
        } else {
          alert.remove();
        }
      }
    }, 10000);
  });
});

document.addEventListener("DOMContentLoaded", function () {
  // Selectors
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("mobileOverlay");
  const toggleBtn = document.getElementById("sidebarToggle");
  const backBtn = document.getElementById("backToTop");

  const themeBtn = document.getElementById("darkModeToggle");
  const navbar = document.querySelector(".navbar");
  const moon = document.getElementById("moonIcon");
  const sun = document.getElementById("sunIcon");

  /* 1. SIDEBAR LOGIC */
  function toggleSidebar() {
    if (window.innerWidth <= 768) {
      sidebar.classList.toggle("mobile-active");
      overlay?.classList.toggle("active");
    } else {
      sidebar.classList.toggle("d-none");
    }
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", function (e) {
      e.preventDefault();
      toggleSidebar();
    });
  }

  if (overlay) {
    overlay.addEventListener("click", toggleSidebar);
  }

  /* 2. THEME TOGGLE (NAVBAR ONLY) */
  function applyTheme(theme) {
    if (theme === "dark") {
      navbar?.classList.add("dark-mode");
      moon?.classList.add("d-none");
      sun?.classList.remove("d-none");
    } else {
      navbar?.classList.remove("dark-mode");
      sun?.classList.add("d-none");
      moon?.classList.remove("d-none");
    }
  }

  themeBtn?.addEventListener("click", () => {
    const isDark = !navbar.classList.contains("dark-mode");
    const themeChoice = isDark ? "dark" : "light";
    localStorage.setItem("theme", themeChoice);
    applyTheme(themeChoice);
  });

  // Load saved theme on startup
  applyTheme(localStorage.getItem("theme") || "light");

  /* 3. BACK TO TOP LOGIC */
  window.addEventListener("scroll", () => {
    if (window.pageYOffset > 300) {
      backBtn.style.display = "flex";
    } else {
      backBtn.style.display = "none";
    }
  });

  backBtn?.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});



$(function () {
        
    $(function () {
        $('#datetimepicker').datetimepicker({
            format: 'Y-m-d H:i',     // Matches Django input format '%Y-%m-%dT%H:%M'
            step: 5,                  // 5-minute increments
            minDate: 0,               // Prevent selecting past dates
            inline: false,            // Pop-up only when input is clicked
            scrollInput: false,
            scrollMonth: false
        });
    });

    const audienceSelect = $('#id_target_audience');
    const listContainer = $('#recipient-list');
    const countSpan = $('#recipient-count');

    function updateCount() {
        countSpan.text($('.recipient-checkbox:checked:visible').length);
    }

    function loadEmails() {
        const val = audienceSelect.val();
        if (!val) return;

        listContainer.html('<p class="text-center py-4">Loading...</p>');

        $.get(window.location.pathname, { audience: val }, function (data) {
            let html = '';
            if (data.emails && data.emails.length) {
                data.emails.forEach(email => {
                    html += `
                    <div class="form-check recipient-row py-2 px-3 border-bottom">
                        <input class="form-check-input recipient-checkbox"
                               type="checkbox" name="final_recipients"
                               value="${email}" checked>
                        <label class="form-check-label small">${email}</label>
                    </div>`;
                });
            }
            listContainer.html(html || '<p class="text-center py-4">No recipients</p>');
            updateCount();
        });
    }

    $('#email-search').on('input', function () {
        const q = $(this).val().toLowerCase();
        $('.recipient-row').each(function () {
            $(this).toggle($(this).text().toLowerCase().includes(q));
        });
        updateCount();
    });

    $('#check-all-toggle').on('change', function () {
        $('.recipient-checkbox:visible').prop('checked', this.checked);
        updateCount();
    });

    // Toggle checkbox when clicking on row
    $(document).on('click', '.recipient-row', function (e) {
        if (!$(e.target).is('input')) {
            const cb = $(this).find('.recipient-checkbox');
            cb.prop('checked', !cb.prop('checked'));
            updateCount();
        }
    });

    $(document).on('change', '.recipient-checkbox', updateCount);

    $(document).on('click', '.delete-btn', function () {
        if (!confirm('Delete this broadcast?')) return;
        $.post($(this).data('url'), {
            csrfmiddlewaretoken: '{{ csrf_token }}'
        }, () => location.reload());
    });

    audienceSelect.on('change', loadEmails);
    if (audienceSelect.val()) loadEmails();
});

// Detect user timezone and store in hidden input
document.addEventListener("DOMContentLoaded", function () {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    document.getElementById("user_timezone").value = tz;
});