// login.js
document.addEventListener('DOMContentLoaded', function() {
    // Toggle password visibility
    const toggleBtns = document.querySelectorAll('.toggle-password');
    
    toggleBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.closest('.input-wrapper').querySelector('input');
            const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
            input.setAttribute('type', type);
            
            // Optional: change icon
            const svg = this.querySelector('svg');
            if (type === 'text') {
                svg.innerHTML = `<path d="M9 4C5 4 2.5 7 1 9C2.5 11 5 14 9 14C13 14 15.5 11 17 9C15.5 7 13 4 9 4Z" stroke="currentColor" stroke-width="1.5" fill="none"/>
                                 <path d="M13 5L5 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                                 <circle cx="9" cy="9" r="2.5" stroke="currentColor" stroke-width="1.5"/>`;
            } else {
                svg.innerHTML = `<path d="M9 4C5 4 2.5 7 1 9C2.5 11 5 14 9 14C13 14 15.5 11 17 9C15.5 7 13 4 9 4Z" stroke="currentColor" stroke-width="1.5"/>
                                 <circle cx="9" cy="9" r="2.5" stroke="currentColor" stroke-width="1.5"/>`;
            }
        });
    });
    
    // Optional: Add floating animation to stats
    const stats = document.querySelectorAll('.stat-value');
    stats.forEach((stat, index) => {
        const value = stat.innerText;
        if (value.includes('+')) {
            // Animate counter if you want
        }
    });
});