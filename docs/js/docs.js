function createIcon(iconName) {
    const icon = document.createElement('i');
    icon.className = `fas fa-${iconName}`;
    return icon;
}

// Documentation-specific JavaScript functionality
document.addEventListener('DOMContentLoaded', function() {
    initializeDocumentationFeatures();
});

function initializeDocumentationFeatures() {
    setupSidebarNavigation();
    setupCodeCopyButtons();
    setupSmoothScrolling();
    setupSearchFunctionality();
    setupTableOfContents();
    setupCodeHighlighting();
    setupResponsiveFeatures();
}

// Sidebar Navigation
function setupSidebarNavigation() {
    const sidebarLinks = document.querySelectorAll('.sidebar-link');
    const sections = document.querySelectorAll('.api-section, .example-section');
    
    // Highlight active section based on scroll position
    function updateActiveSection() {
        let current = '';
        
        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.clientHeight;
            
            if (pageYOffset >= sectionTop - 200) {
                current = section.getAttribute('id');
            }
        });
        
        // Update sidebar links
        sidebarLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${current}`) {
                link.classList.add('active');
            }
        });
    }
    
    // Smooth scroll for sidebar links
    sidebarLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').substring(1);
            const targetSection = document.getElementById(targetId);
            
            if (targetSection) {
                targetSection.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
    
    // Update active section on scroll
    window.addEventListener('scroll', updateActiveSection);
    
    // Initial call
    updateActiveSection();
}

// Code Copy Functionality
function setupCodeCopyButtons() {
    const codeBlocks = document.querySelectorAll('pre code');
    
    codeBlocks.forEach(codeBlock => {
        const pre = codeBlock.parentElement;
        
        // Create copy button
        const copyButton = document.createElement('button');
        copyButton.className = 'copy-code-btn';
        copyButton.appendChild(createIcon('copy'));
        copyButton.title = 'Copy code';
        
        // Position button
        pre.style.position = 'relative';
        pre.appendChild(copyButton);
        
        // Copy functionality
        copyButton.addEventListener('click', async function() {
            try {
                await navigator.clipboard.writeText(codeBlock.textContent);
                
                // Visual feedback
                this.replaceChildren(createIcon('check'));
                this.style.color = '#4CAF50';
                
                setTimeout(() => {
                    this.replaceChildren(createIcon('copy'));
                    this.style.color = '';
                }, 2000);
                
                // Show toast notification
                showToast('Code copied to clipboard!', 'success');
                
            } catch (err) {
                console.error('Failed to copy code:', err);
                showToast('Failed to copy code', 'error');
            }
        });
    });
}

// Enhanced Smooth Scrolling
function setupSmoothScrolling() {
    // Handle all internal links
    document.querySelectorAll('a[href^="#"]').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            const targetId = this.getAttribute('href').substring(1);
            const targetElement = document.getElementById(targetId);
            
            if (targetElement) {
                const offsetTop = targetElement.offsetTop - 100; // Account for navbar
                
                window.scrollTo({
                    top: offsetTop,
                    behavior: 'smooth'
                });
            }
        });
    });
}

// Search Functionality
function setupSearchFunctionality() {
    // Create search input if it doesn't exist
    const sidebar = document.querySelector('.docs-sidebar .sidebar-content');
    if (sidebar && !document.querySelector('.docs-search')) {
        const searchContainer = document.createElement('div');
        searchContainer.className = 'docs-search';
        const inputContainer = document.createElement('div');
        inputContainer.className = 'search-input-container';
        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.id = 'docs-search-input';
        searchInput.placeholder = 'Search documentation...';
        const searchIcon = createIcon('search');
        searchIcon.classList.add('search-icon');
        const searchResults = document.createElement('div');
        searchResults.id = 'search-results';
        searchResults.className = 'search-results';
        inputContainer.append(searchInput, searchIcon);
        searchContainer.append(inputContainer, searchResults);
        
        // Insert search at the top of sidebar
        sidebar.insertBefore(searchContainer, sidebar.firstChild);
        
        setupSearchInput();
    }
}

function setupSearchInput() {
    const searchInput = document.getElementById('docs-search-input');
    const searchResults = document.getElementById('search-results');
    
    if (!searchInput) return;
    
    let searchTimeout;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim().toLowerCase();
        
        if (query.length < 2) {
            searchResults.replaceChildren();
            searchResults.style.display = 'none';
            return;
        }
        
        searchTimeout = setTimeout(() => {
            performSearch(query);
        }, 300);
    });
    
    // Close search results when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.docs-search')) {
            searchResults.style.display = 'none';
        }
    });
}

function performSearch(query) {
    const searchResults = document.getElementById('search-results');
    const sections = document.querySelectorAll('.api-section, .example-section');
    const results = [];
    
    sections.forEach(section => {
        const sectionId = section.id;
        const sectionTitle = section.querySelector('h2')?.textContent || '';
        const sectionContent = section.textContent.toLowerCase();
        
        if (sectionContent.includes(query)) {
            // Find specific matches within the section
            const methods = section.querySelectorAll('.method-card h3, .example-card h3');
            methods.forEach(method => {
                if (method.textContent.toLowerCase().includes(query)) {
                    results.push({
                        title: method.textContent,
                        section: sectionTitle,
                        id: sectionId,
                        type: 'method'
                    });
                }
            });
            
            // Add section match if no specific methods found
            if (sectionTitle.toLowerCase().includes(query)) {
                results.push({
                    title: sectionTitle,
                    section: '',
                    id: sectionId,
                    type: 'section'
                });
            }
        }
    });
    
    displaySearchResults(results, query);
}

function displaySearchResults(results, query) {
    const searchResults = document.getElementById('search-results');
    searchResults.replaceChildren();

    if (results.length === 0) {
        const emptyResult = document.createElement('div');
        emptyResult.className = 'search-no-results';
        emptyResult.textContent = 'No results found';
        searchResults.appendChild(emptyResult);
    } else {
        results.slice(0, 8).forEach(result => {
            const item = document.createElement('div');
            item.className = 'search-result-item';
            item.addEventListener('click', () => navigateToResult(result.id));

            const title = document.createElement('div');
            title.className = 'search-result-title';
            appendHighlightedText(title, result.title, query);
            item.appendChild(title);

            if (result.section) {
                const section = document.createElement('div');
                section.className = 'search-result-section';
                section.textContent = result.section;
                item.appendChild(section);
            }

            const type = document.createElement('div');
            type.className = 'search-result-type';
            type.textContent = result.type;
            item.appendChild(type);
            searchResults.appendChild(item);
        });
    }

    searchResults.style.display = 'block';
}

function appendHighlightedText(container, text, query) {
    const source = String(text);
    const normalizedSource = source.toLowerCase();
    const normalizedQuery = String(query).toLowerCase();
    if (!normalizedQuery) {
        container.textContent = source;
        return;
    }

    let cursor = 0;
    let matchIndex = normalizedSource.indexOf(normalizedQuery, cursor);
    while (matchIndex !== -1) {
        container.appendChild(document.createTextNode(source.slice(cursor, matchIndex)));
        const mark = document.createElement('mark');
        mark.textContent = source.slice(matchIndex, matchIndex + normalizedQuery.length);
        container.appendChild(mark);
        cursor = matchIndex + normalizedQuery.length;
        matchIndex = normalizedSource.indexOf(normalizedQuery, cursor);
    }
    container.appendChild(document.createTextNode(source.slice(cursor)));
}

function navigateToResult(sectionId) {
    const targetElement = document.getElementById(sectionId);
    if (targetElement) {
        targetElement.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
        
        // Hide search results
        document.getElementById('search-results').style.display = 'none';
        
        // Clear search input
        document.getElementById('docs-search-input').value = '';
    }
}

// Table of Contents Generation
function setupTableOfContents() {
    const tocContainer = document.querySelector('.table-of-contents');
    if (!tocContainer) return;
    
    const headings = document.querySelectorAll('.docs-content h2, .docs-content h3');
    const tocList = document.createElement('ul');
    tocList.className = 'toc-list';
    
    headings.forEach((heading, index) => {
        const id = heading.id || `heading-${index}`;
        if (!heading.id) {
            heading.id = id;
        }
        
        const tocItem = document.createElement('li');
        tocItem.className = `toc-item toc-${heading.tagName.toLowerCase()}`;
        
        const tocLink = document.createElement('a');
        tocLink.href = `#${id}`;
        tocLink.textContent = heading.textContent;
        tocLink.className = 'toc-link';
        
        tocItem.appendChild(tocLink);
        tocList.appendChild(tocItem);
    });
    
    tocContainer.appendChild(tocList);
}

// Enhanced Code Highlighting
function setupCodeHighlighting() {
    // Add language labels to code blocks
    const codeBlocks = document.querySelectorAll('pre code[class*="language-"]');
    
    codeBlocks.forEach(codeBlock => {
        const pre = codeBlock.parentElement;
        const language = codeBlock.className.match(/language-(\w+)/)?.[1];
        
        if (language) {
            const languageLabel = document.createElement('div');
            languageLabel.className = 'code-language-label';
            languageLabel.textContent = language.toUpperCase();
            
            pre.style.position = 'relative';
            pre.insertBefore(languageLabel, codeBlock);
        }
    });
    
    // Add line numbers for longer code blocks
    addLineNumbers();
}

function addLineNumbers() {
    const codeBlocks = document.querySelectorAll('pre code');
    
    codeBlocks.forEach(codeBlock => {
        const lines = codeBlock.textContent.split('\n');
        
        // Only add line numbers for code blocks with more than 10 lines
        if (lines.length > 10) {
            const pre = codeBlock.parentElement;
            pre.classList.add('line-numbers');
            
            const lineNumbersDiv = document.createElement('div');
            lineNumbersDiv.className = 'line-numbers-rows';
            
            for (let i = 1; i <= lines.length; i++) {
                const lineNumber = document.createElement('span');
                lineNumber.textContent = i;
                lineNumbersDiv.appendChild(lineNumber);
            }
            
            pre.appendChild(lineNumbersDiv);
        }
    });
}

// Responsive Features
function setupResponsiveFeatures() {
    const sidebar = document.querySelector('.docs-sidebar');
    const content = document.querySelector('.docs-content');
    
    if (!sidebar || !content) return;
    
    // Mobile sidebar toggle
    createMobileSidebarToggle();
    
    // Adjust layout on window resize
    window.addEventListener('resize', adjustLayout);
    adjustLayout(); // Initial call
}

function createMobileSidebarToggle() {
    const navbar = document.querySelector('.navbar .nav-container');
    const sidebar = document.querySelector('.docs-sidebar');
    
    if (!navbar || !sidebar) return;
    
    // Create toggle button
    const toggleButton = document.createElement('button');
    toggleButton.className = 'docs-sidebar-toggle';
    toggleButton.appendChild(createIcon('bars'));
    toggleButton.title = 'Toggle documentation sidebar';
    
    // Add to navbar
    navbar.appendChild(toggleButton);
    
    // Toggle functionality
    toggleButton.addEventListener('click', function() {
        sidebar.classList.toggle('sidebar-open');
        document.body.classList.toggle('sidebar-overlay');
        
        // Update icon
        const icon = this.querySelector('i');
        if (sidebar.classList.contains('sidebar-open')) {
            icon.className = 'fas fa-times';
        } else {
            icon.className = 'fas fa-bars';
        }
    });
    
    // Close sidebar when clicking overlay
    document.addEventListener('click', function(e) {
        if (document.body.classList.contains('sidebar-overlay') && 
            !e.target.closest('.docs-sidebar') && 
            !e.target.closest('.docs-sidebar-toggle')) {
            
            sidebar.classList.remove('sidebar-open');
            document.body.classList.remove('sidebar-overlay');
            toggleButton.querySelector('i').className = 'fas fa-bars';
        }
    });
}

function adjustLayout() {
    const sidebar = document.querySelector('.docs-sidebar');
    const isMobile = window.innerWidth <= 768;
    
    if (sidebar) {
        if (isMobile) {
            sidebar.classList.add('mobile-sidebar');
        } else {
            sidebar.classList.remove('mobile-sidebar', 'sidebar-open');
            document.body.classList.remove('sidebar-overlay');
        }
    }
}

// Toast Notification System
function showToast(message, type = 'info', duration = 3000) {
    const existingToasts = document.querySelectorAll('.toast');
    existingToasts.forEach(toast => toast.remove());

    const safeType = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'info';
    const toast = document.createElement('div');
    toast.className = `toast toast-${safeType}`;
    const content = document.createElement('div');
    content.className = 'toast-content';
    const icon = document.createElement('i');
    icon.className = `fas fa-${getToastIcon(safeType)}`;
    const text = document.createElement('span');
    text.textContent = String(message);
    content.append(icon, text);

    const closeButton = document.createElement('button');
    closeButton.className = 'toast-close';
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', 'Close notification');
    const closeIcon = document.createElement('i');
    closeIcon.className = 'fas fa-times';
    closeButton.appendChild(closeIcon);
    toast.append(content, closeButton);
    document.body.appendChild(toast);
    
    // Show toast
    setTimeout(() => toast.classList.add('toast-show'), 100);
    
    // Auto hide
    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
    
    // Manual close
    closeButton.addEventListener('click', () => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    });
}

function getToastIcon(type) {
    const icons = {
        success: 'check-circle',
        error: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    return icons[type] || icons.info;
}

// Utility Functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Method Cards Animation
function animateMethodCards() {
    const methodCards = document.querySelectorAll('.method-card, .example-card');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    });
    
    methodCards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(card);
    });
}

// Initialize animations when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(animateMethodCards, 500);
});

// Back to Top Button
function createBackToTopButton() {
    const backToTop = document.createElement('button');
    backToTop.className = 'back-to-top';
    backToTop.appendChild(createIcon('arrow-up'));
    backToTop.title = 'Back to top';
    
    document.body.appendChild(backToTop);
    
    // Show/hide based on scroll position
    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 500) {
            backToTop.classList.add('show');
        } else {
            backToTop.classList.remove('show');
        }
    });
    
    // Scroll to top functionality
    backToTop.addEventListener('click', () => {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

// Initialize back to top button
document.addEventListener('DOMContentLoaded', createBackToTopButton);

// Print-friendly functionality
function setupPrintStyles() {
    const printButton = document.createElement('button');
    printButton.className = 'print-button';
    printButton.append(createIcon('print'), document.createTextNode(' Print'));
    printButton.title = 'Print this page';
    
    const docsHeader = document.querySelector('.docs-header');
    if (docsHeader) {
        docsHeader.appendChild(printButton);
        
        printButton.addEventListener('click', () => {
            window.print();
        });
    }
}

// Initialize print functionality
document.addEventListener('DOMContentLoaded', setupPrintStyles);
