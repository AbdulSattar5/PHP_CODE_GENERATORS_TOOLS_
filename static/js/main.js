/**
 * GenCode AI — global UI (ChatGPT-style sidebar + utilities)
 */

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (!sidebar) return;

    if (window.innerWidth <= 768) {
        const isOpen = sidebar.classList.contains('show');
        if (isOpen) {
            closeSidebar();
        } else {
            sidebar.classList.add('show');
            overlay?.classList.add('show');
            document.body.style.overflow = 'hidden';
        }
        return;
    }

    sidebar.classList.toggle('collapsed');
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (sidebar) {
        sidebar.classList.remove('show');
        sidebar.classList.remove('collapsed');
    }
    overlay?.classList.remove('show');
    document.body.style.overflow = '';
}

function closeMobileSidebar() {
    closeSidebar();
}

function toggleMobileSidebar() {
    toggleSidebar();
}

function startNewChat(event) {
    if (event) event.preventDefault();
    window.location.href = '/generate/';
}

function toggleNavDropdown(event, button) {
    event.preventDefault();
    event.stopPropagation();
    const navItem = button.closest('.nav-item');
    if (!navItem) return;

    document.querySelectorAll('.nav-dropdown').forEach((menu) => {
        if (!navItem.contains(menu)) {
            menu.classList.add('hidden');
        }
    });

    const dropdown = navItem.querySelector('.nav-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('hidden');
    }
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.nav-item')) {
        document.querySelectorAll('.nav-dropdown').forEach((menu) => menu.classList.add('hidden'));
    }

    if (window.innerWidth <= 768) {
        if (!e.target.closest('.sidebar') && !e.target.closest('.mobile-menu-btn')) {
            closeSidebar();
        }
    }
});

document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 && e.target.closest('[data-nav-item]')) {
        setTimeout(closeSidebar, 100);
    }
});

window.addEventListener('resize', () => {
    if (window.innerWidth > 768) {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        sidebar?.classList.remove('show');
        overlay?.classList.remove('show');
        document.body.style.overflow = '';
    }
});

document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 's') {
        e.preventDefault();
        toggleSidebar();
    }
});

document.addEventListener('click', (e) => {
    const modals = document.querySelectorAll('.modal');
    modals.forEach((modal) => {
        if (e.target === modal) {
            modal.classList.remove('show');
        }
    });
});

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${Math.round((bytes / Math.pow(k, i)) * 100) / 100} ${sizes[i]}`;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffDays = Math.ceil(Math.abs(now - date) / (1000 * 60 * 60 * 24));
    if (diffDays <= 1) return 'Today';
    if (diffDays === 2) return 'Yesterday';
    if (diffDays < 7) return `${diffDays - 1} days ago`;
    return date.toLocaleDateString();
}

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (error) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            return true;
        } catch (err) {
            return false;
        } finally {
            document.body.removeChild(textArea);
        }
    }
}

function downloadFile(content, filename, contentType = 'text/plain') {
    const blob = new Blob([content], { type: contentType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), wait);
    };
}

function showNotification(message, type = 'info', duration = 5000) {
    let container = document.querySelector('.messages-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'messages-container';
        document.body.appendChild(container);
    }

    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.innerHTML = `
        <i class="fas fa-info-circle"></i>
        ${message}
        <button type="button" class="close-btn" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    container.appendChild(notification);

    if (duration > 0) {
        setTimeout(() => notification.remove(), duration);
    }
    return notification;
}

document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form');
    forms.forEach((form) => {
        form.addEventListener('submit', (e) => {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled && !form.id?.includes('newProject')) {
                const originalText = submitBtn.innerHTML;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                submitBtn.disabled = true;
                setTimeout(() => {
                    submitBtn.innerHTML = originalText;
                    submitBtn.disabled = false;
                }, 10000);
            }
        });
    });
});
