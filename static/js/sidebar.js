/**
 * Sidebar search + nav helpers
 */
function initSidebarSearch() {
    const input = document.getElementById('sidebarSearchInput');
    if (!input) return;

    input.addEventListener('input', () => {
        const q = input.value.trim().toLowerCase();
        document.querySelectorAll('.sidebar-nav .nav-item').forEach((item) => {
            const text = item.querySelector('.nav-item-text')?.textContent?.toLowerCase() || '';
            item.classList.toggle('hidden', q.length > 0 && !text.includes(q));
        });
        document.querySelectorAll('.sidebar-nav .nav-section').forEach((section) => {
            const visible = section.querySelectorAll('.nav-item:not(.hidden)').length;
            section.classList.toggle('hidden', q.length > 0 && visible === 0);
        });
    });
}

function toggleUserMenu() {
    const menu = document.getElementById('userMenu');
    if (menu) menu.classList.toggle('show');
}

document.addEventListener('DOMContentLoaded', () => {
    initSidebarSearch();
});
