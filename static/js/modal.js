// ===== MODAL SYSTEM =====
window.WMS = window.WMS || {};

// Open modal with animations
window.WMS.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    modal.style.display = 'flex';
    document.body.classList.add('modal-open');
    
    // Trigger animation on next frame
    requestAnimationFrame(() => {
        modal.classList.add('active');
    });
};

// Close modal with animations
window.WMS.closeModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    modal.classList.remove('active');
    document.body.classList.remove('modal-open');
    
    // Wait for animation then hide
    setTimeout(() => {
        modal.style.display = 'none';
    }, 250);
};

// Setup all modals on page: close on overlay click, ESC key, close buttons
window.WMS.setupModals = function() {
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        // Close on overlay click (but not content click)
        overlay.addEventListener('click', function(e) {
            if (e.target === this) {
                window.WMS.closeModal(this.id);
            }
        });
        
        // Close button inside modal header
        const closeBtn = overlay.querySelector('.modal-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => window.WMS.closeModal(overlay.id));
        }
    });
    
    // ESC key to close latest modal
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const activeModal = document.querySelector('.modal-overlay.active');
            if (activeModal) {
                window.WMS.closeModal(activeModal.id);
            }
        }
    });
};

// Auto-setup on DOM ready
document.addEventListener('DOMContentLoaded', window.WMS.setupModals);

// ===== CONFIRM DIALOG (modern replacement for alert/confirm) =====
window.WMS.confirm = function(message, title = 'Xác nhận') {
    return new Promise((resolve) => {
        const existing = document.getElementById('wms-confirm-dialog');
        if (existing) existing.remove();
        
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.id = 'wms-confirm-dialog';
        overlay.style.cssText = 'display:flex;';
        
        overlay.innerHTML = `
            <div class="modal-content modal-sm" style="transform:translateY(0);opacity:1;">
                <div class="modal-header">
                    <h3>${window.WMS.escapeHtml(title)}</h3>
                </div>
                <div class="modal-body" style="font-size:15px;color:#475569;">
                    ${window.WMS.escapeHtml(message)}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" id="confirm-cancel-btn">Hủy</button>
                    <button class="btn btn-primary" id="confirm-ok-btn">Đồng ý</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        document.body.classList.add('modal-open');
        
        requestAnimationFrame(() => overlay.classList.add('active'));
        
        document.getElementById('confirm-ok-btn').onclick = () => {
            window.WMS.closeModal('wms-confirm-dialog');
            setTimeout(() => overlay.remove(), 300);
            resolve(true);
        };
        
        document.getElementById('confirm-cancel-btn').onclick = () => {
            window.WMS.closeModal('wms-confirm-dialog');
            setTimeout(() => overlay.remove(), 300);
            resolve(false);
        };
        
        overlay.onclick = (e) => {
            if (e.target === overlay) {
                window.WMS.closeModal('wms-confirm-dialog');
                setTimeout(() => overlay.remove(), 300);
                resolve(false);
            }
        };
    });
};

// ===== ALERT DIALOG =====
window.WMS.alert = function(message, title = 'Thông báo') {
    return new Promise((resolve) => {
        const existing = document.getElementById('wms-alert-dialog');
        if (existing) existing.remove();
        
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.id = 'wms-alert-dialog';
        overlay.style.cssText = 'display:flex;';
        
        overlay.innerHTML = `
            <div class="modal-content modal-sm" style="transform:translateY(0);opacity:1;">
                <div class="modal-header">
                    <h3>${window.WMS.escapeHtml(title)}</h3>
                </div>
                <div class="modal-body" style="font-size:15px;color:#475569;">
                    ${window.WMS.escapeHtml(message)}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" id="alert-ok-btn">Đồng ý</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        document.body.classList.add('modal-open');
        
        requestAnimationFrame(() => overlay.classList.add('active'));
        
        document.getElementById('alert-ok-btn').onclick = () => {
            window.WMS.closeModal('wms-alert-dialog');
            setTimeout(() => overlay.remove(), 300);
            resolve();
        };
        
        overlay.onclick = (e) => {
            if (e.target === overlay) {
                window.WMS.closeModal('wms-alert-dialog');
                setTimeout(() => overlay.remove(), 300);
                resolve();
            }
        };
    });
};