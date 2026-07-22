function useImage(url, id) {
    // If opened in a popup/iframe, send data to the parent
    if (window.opener) {
        // Option A: If opened via window.open
        window.opener.handleVisualSelection(url, id);
        window.close();
    } else if (window.parent) {
        // Option B: If opened via iframe in a Modal
        window.parent.handleVisualSelection(url, id);
    }
}
    const wrapper = document.getElementById('ajax-table-wrapper');

    function getFilters() {
        return {
            q: document.getElementById('ajaxSearch').value,
            cat: document.getElementById('albumFilter').value,
            entries: document.getElementById('entriesCount').value,
            page: document.getElementById('customPageInput') ? document.getElementById('customPageInput').value : 1
        };
    }

    async function fetchData(params = {}) {
        const filters = getFilters();
        const searchParams = new URLSearchParams({...filters, ...params});
        const url = `${window.location.pathname}?${searchParams.toString()}`;
        
        wrapper.style.opacity = '0.4';
        
        try {
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            const html = await response.text();
            
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const newTable = doc.getElementById('ajax-table-wrapper').innerHTML;
            
            wrapper.innerHTML = newTable;
            // Update the browser URL without refreshing
            window.history.pushState({}, '', url);
        } catch (err) {
            console.error("Error loading data:", err);
        } finally {
            wrapper.style.opacity = '1';
            bindDynamicEvents();
        }
    }

    function bindDynamicEvents() {
        // Pagination link clicks
        document.querySelectorAll('.ajax-page').forEach(link => {
            link.onclick = (e) => {
                e.preventDefault();
                const page = new URL(link.href).searchParams.get('page');
                fetchData({ page });
            };
        });

        // Custom Page Input
        const pageInput = document.getElementById('customPageInput');
        if (pageInput) {
            pageInput.onchange = () => fetchData({ page: pageInput.value });
        }

        // Header Checkbox (Select All)
        const headerCheck = document.getElementById('selectAllHeader');
        if (headerCheck) {
            headerCheck.onclick = () => {
                document.querySelectorAll('.asset-checkbox').forEach(cb => cb.checked = headerCheck.checked);
            };
        }
    }

    // Input Listeners with Debounce
    let timer;
    document.getElementById('ajaxSearch').addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => fetchData({ page: 1 }), 500);
    });

    document.getElementById('albumFilter').addEventListener('change', () => fetchData({ page: 1 }));
    document.getElementById('entriesCount').addEventListener('change', () => fetchData({ page: 1 }));

    // Actions
    function deleteSingle(id) {
        if (confirm('Delete this file permanently?')) {
            const formData = new FormData();
            formData.append('bulk_action', 'delete');
            formData.append('asset_ids', id);
            formData.append('csrfmiddlewaretoken', '{{ csrf_token }}');

            fetch(window.location.href, {
                method: 'POST',
                body: formData
            }).then(() => fetchData());
        }
    }

    function copyToClipboard(text, btn) {
        navigator.clipboard.writeText(text).then(() => {
            const oldText = btn.innerText;
            btn.innerText = "Copied!";
            btn.classList.replace('btn-info', 'btn-success');
            setTimeout(() => {
                btn.innerText = oldText;
                btn.classList.replace('btn-success', 'btn-info');
            }, 1500);
        });
    }

    // Initialize events on page load
    document.addEventListener('DOMContentLoaded', bindDynamicEvents);



    
/**
 * GLOBAL MEDIA PICKER HANDLER
 */
window.activeTarget = '';

window.openPicker = function(target, libraryUrl) {
    window.activeTarget = target;
    const isBulk = (target === 'gallery') ? '&mode=bulk' : '';
    const separator = libraryUrl.includes('?') ? '&' : '?';
    const finalUrl = libraryUrl + separator + "type=picker&target=" + target + isBulk;
    window.open(finalUrl, "MediaPicker", "width=1100,height=700");
};

window.handleVisualSelection = function(url, id, title = '', target = '') {
    const finalTarget = target || window.activeTarget;
    const urlList = Array.isArray(url) ? url : [url];
    const idList = Array.isArray(id) ? id : [id];

    if (finalTarget === 'gallery') {
        const container = document.getElementById('gallery-container');
        if (container) {
            urlList.forEach((u, i) => {
                const markup = `
                    <div class="col-4 gallery-item mb-2">
                        <div class="position-relative border rounded overflow-hidden" style="height: 80px;">
                            ${window.generateMediaMarkup(u, true)}
                            <input type="hidden" name="gallery_asset_ids" value="${idList[i]}">
                            <button type="button" class="btn btn-danger btn-sm position-absolute top-0 end-0 p-0 px-1" 
                                    onclick="this.closest('.gallery-item').remove()">×</button>
                        </div>
                    </div>`;
                container.insertAdjacentHTML('beforeend', markup);
            });
        }
    } else {
        const input = document.getElementById(`id_is_${finalTarget}_id`);
        const previewDiv = document.getElementById(`${finalTarget}-preview`);
        const titleText = document.getElementById(`${finalTarget}-title`);

        if (input && previewDiv) {
            input.value = idList[0];
            // Update Title if element exists
            if (titleText) titleText.innerText = title || "Asset ID: " + idList[0];
            
            // Inject Red "X" and Media
            previewDiv.innerHTML = `
                <button type="button" class="btn btn-danger btn-sm position-absolute" 
                        style="top: 8px; right: 8px; z-index: 10; width: 28px; height: 28px; padding: 0;" 
                        onclick="window.clearMediaSelection('${finalTarget}')">
                    <i class="bi bi-x"></i>
                </button>
                ${window.generateMediaMarkup(urlList[0])}`;
        }
    }
};

window.generateMediaMarkup = function(url, isGallery = false) {
    const isVideo = url.match(/\.(mp4|webm|mov|ogg)$/i);
    const css = isGallery ? "w-100 h-100 object-fit-cover" : "h-100 w-100 object-fit-contain";
    return isVideo ? `<video src="${url}" class="${css}" autoplay muted loop playsinline></video>` : `<img src="${url}" class="${css}">`;
};

window.clearMediaSelection = function(target) {
    const input = document.getElementById(`id_is_${target}_id`);
    const previewDiv = document.getElementById(`${target}-preview`);
    const titleText = document.getElementById(`${target}-title`);

    if (input) input.value = '';
    if (titleText) titleText.innerText = "No image selected";
    if (previewDiv) {
        previewDiv.innerHTML = `
            <div class="text-center">
                <i class="bi bi-camera text-muted fs-2"></i>
            </div>`;
    }
};

const typingNode = document.createElement('div');
typingNode.id = 'aiTyping';

typingNode.innerHTML = `
<div class="d-flex justify-content-start mb-2">
    <div class="bg-light p-2 rounded">
        AI Assistant is typing...
    </div>
</div>
`;

chatCanvas.appendChild(typingNode);
scrollBottom();