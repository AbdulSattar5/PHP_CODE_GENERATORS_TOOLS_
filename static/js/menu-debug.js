// Menu Debug Script
// Add this to test mobile menu functionality

console.log('Menu Debug Script Loaded');

// Test function to check if elements exist
function debugMenu() {
    console.log('=== MENU DEBUG ===');

    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const menuToggle = document.querySelector('.mobile-menu-toggle');

    console.log('Sidebar element:', sidebar);
    console.log('Overlay element:', overlay);
    console.log('Menu toggle button:', menuToggle);

    if (sidebar) {
        console.log('Sidebar classes:', sidebar.className);
        console.log('Sidebar computed style display:', window.getComputedStyle(sidebar).display);
        console.log('Sidebar computed style transform:', window.getComputedStyle(sidebar).transform);
    }

    if (overlay) {
        console.log('Overlay classes:', overlay.className);
        console.log('Overlay computed style display:', window.getComputedStyle(overlay).display);
        console.log('Overlay computed style opacity:', window.getComputedStyle(overlay).opacity);
    }

    console.log('Window width:', window.innerWidth);
    console.log('Is mobile?', window.innerWidth <= 768);
}

// Test toggle function
function testToggle() {
    console.log('Testing toggle...');
    debugMenu();
    toggleMobileSidebar();
    setTimeout(() => {
        console.log('After toggle:');
        debugMenu();
    }, 500);
}

// Add to window for console access
window.debugMenu = debugMenu;
window.testToggle = testToggle;

// Auto-run debug on load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(debugMenu, 1000);
});