from bs4 import BeautifulSoup
import requests

# Common Class Names for Pagination Elements

# Container Classes
container_classes = [
    "pagination",
    "pagination-container",
    "pagination-wrapper"
]

# Page Item Classes
page_item_classes = [
    "page-item",
    "pagination__item",
    "pagination-page"
]

# Link Classes
link_classes = [
    "page-link",
    "pagination__link",
    "pagination-link"
]

# Active Page Classes
active_page_classes = [
    "active",
    "is-active",
    "current",
    "pagination__active"
]

# Disabled State Classes
disabled_state_classes = [
    "disabled",
    "is-disabled",
    "pagination__disabled"
]

# Previous/Next Button Classes
prev_next_button_classes = [
    "prev",
    "next",
    "pagination-prev",
    "pagination-next",
    "pagination__prev",
    "pagination__next"
]

# Ellipsis Classes (for indicating skipped pages)
ellipsis_classes = [
    "ellipsis",
    "pagination-ellipsis",
    "pagination__ellipsis"
]

# Tool 1: find_page_nav
def find_page_nav(soup, container_classes):
    for container_class in container_classes:
        pagination_container = soup.find('div', class_=container_class)
        if pagination_container:
            return pagination_container
    return None

# Tool 2: extract_pages
def extract_pages(pagination_container):
    pages = {}
    for link in pagination_container.find_all('a', class_='page-link'):
        href = link.get('href')
        if href and 'javascript' not in href:
            page_number = link.text.strip()
            pages[page_number] = href
    return pages

# Main Tool: get_pagination_links
def get_page_links(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Common Class Names for Pagination Elements
    container_classes = [
        "pagination",
        "pagination-container",
        "pagination-wrapper"
    ]
    
    pagination_container = find_page_nav(soup, container_classes)
    if not pagination_container:
        return {}
    
    pages = extract_pages(pagination_container)
    return pages


    PAGE_NAVIGATION_TOOLS = [find_page_nav, get_page_links, extract_pages]