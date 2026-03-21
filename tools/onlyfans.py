import time
import requests
import functools
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from langchain.tools import tool

# ======================
# CONSTANTS
# ======================
MESSAGES_PAGE = "https://onlyfans.com/my/chats"
CONVERSATION_CLASS = "b-chats__item"
MESSAGE_CLASS = "b-chat__message"
MEDIA_WRAPPER_CLASS = "b-chat__message__media-wrapper"
IMAGE_CLASS = "b-post__media__img"
VIDEO_CLASS = "vjs-tech"
SOURCE_ATTRIBUTE = "src"
SCROLLER_CLASS = "b-chats__scroller"
INFINITE_STATUS_PROMPT_CLASS = "infinite-status-prompt"

# ======================
# RETRY DECORATOR
# ======================
def retry(max_retries=3, delay=2):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    print(f"[{func.__name__}] Attempt {attempt+1} failed: {e}")
                    time.sleep(delay)
            print(f"[{func.__name__}] Failed after {max_retries} attempts")
            raise last_error
        return wrapper
    return decorator

# ======================
# HELPERS
# ======================
def safe_find(element, by, value):
    try:
        return element.find_element(by, value)
    except:
        return None

# ======================
# TOOLS
# ======================

@tool("login_to_onlyfans")
@retry()
def login_to_onlyfans(email=None, password=None):
    """
    Log into OnlyFans and return an authenticated Selenium WebDriver session.

    Args:
        email (str, optional): OnlyFans account email. If not provided, uses ONLYFANS_EMAIL env var.
        password (str, optional): OnlyFans account password. If not provided, uses ONLYFANS_PASSWORD env var.

    Returns:
        WebDriver: Authenticated Firefox Selenium driver positioned on the messages page.

    Notes:
        - Required before calling any scraping tools.
        - Maintains login session for subsequent tool calls.
    """
    import os

    email = email or os.getenv('ONLYFANS_EMAIL')
    password = password or os.getenv('ONLYFANS_PASSWORD')

    if not email or not password:
        raise ValueError("Missing credentials")

    firefox_options = Options()
    firefox_options.accept_insecure_certs = True

    service = Service('/home/ermer/.local/bin/geckodriver')
    driver = webdriver.Firefox(service=service, options=firefox_options)

    driver.get('https://onlyfans.com')
    time.sleep(2)

    driver.find_element(By.NAME, 'email').send_keys(email)
    driver.find_element(By.NAME, 'password').send_keys(password)
    driver.find_element(By.XPATH, '//button[@type="submit"]').click()

    time.sleep(5)
    driver.get(MESSAGES_PAGE)

    return driver


@tool("scroll_conversations")
@retry()
def scroll_conversations(driver):
    """
    Scroll through the OnlyFans conversations list until all conversations are loaded.

    Args:
        driver (WebDriver): Authenticated Selenium driver.

    Behavior:
        - Continuously scrolls the conversation sidebar
        - Stops when no additional conversations load

    Use when:
        - You need to access all conversations before iterating through them
    """
    scroller = driver.find_element(By.CLASS_NAME, SCROLLER_CLASS)
    last_height = 0

    while True:
        driver.execute_script(
            "arguments[0].scrollTo(0, arguments[0].scrollHeight);",
            scroller
        )
        time.sleep(2)

        new_height = scroller.size['height']
        if new_height == last_height:
            break

        last_height = new_height


@tool("scroll_messages")
@retry()
def scroll_messages(driver):
    """
    Scroll the currently open conversation to load additional messages.

    Args:
        driver (WebDriver): Active Selenium driver currently inside a conversation.

    Behavior:
        - Scrolls message container downward once
        - Triggers lazy loading of older messages

    Use repeatedly to fully load message history.
    """
    scroller = driver.find_element(By.CLASS_NAME, SCROLLER_CLASS)

    driver.execute_script(
        "arguments[0].scrollTo(0, arguments[0].scrollHeight);",
        scroller
    )
    time.sleep(2)


@tool("extract_images_and_videos")
@retry()
def extract_images_and_videos(driver, save_dir):
    """
    Extract all images and videos from the currently open conversation and save them locally.

    Args:
        driver (WebDriver): Active Selenium driver inside a conversation.
        save_dir (str): Directory path where media files will be saved.

    Behavior:
        - Iterates through messages
        - Downloads images and videos found in message media blocks
        - Continues scrolling until no more content is available

    Output:
        Saves media files to disk using save_image and save_video tools.
    """

    while True:
        scroll_messages(driver)

        messages = driver.find_elements(By.CLASS_NAME, MESSAGE_CLASS)

        for msg_i, message in enumerate(messages):
            try:
                media_wrapper = safe_find(message, By.CLASS_NAME, MEDIA_WRAPPER_CLASS)
                if not media_wrapper:
                    continue

                images = media_wrapper.find_elements(By.CLASS_NAME, IMAGE_CLASS)

                for i, img in enumerate(images):
                    src = img.get_attribute("src")
                    if src:
                        save_image(src, f"{save_dir}/image_{msg_i}_{i}.jpg")

                videos = media_wrapper.find_elements(By.CLASS_NAME, VIDEO_CLASS)

                for i, video in enumerate(videos):
                    sources = video.find_elements(By.TAG_NAME, "source")
                    for j, source in enumerate(sources):
                        src = source.get_attribute(SOURCE_ATTRIBUTE)
                        if src:
                            save_video(src, f"{save_dir}/video_{msg_i}_{i}_{j}.mp4")

            except Exception as e:
                print(f"[message {msg_i}] skipped: {e}")
                continue

        try:
            status = driver.find_element(By.CSS_SELECTOR, INFINITE_STATUS_PROMPT_CLASS)
            if "hidden" in status.get_attribute("class"):
                break
        except:
            break


@tool("extract_media")
@retry()
def extract_media(driver, save_dir):
    """
    Extract media from all conversations in the user's OnlyFans inbox.

    Args:
        driver (WebDriver): Authenticated Selenium driver.
        save_dir (str): Directory to store downloaded media.

    Behavior:
        - Loads messages page
        - Scrolls and loads all conversations
        - Iterates through each conversation
        - Extracts all images and videos

    This is the main high-level scraping entrypoint.
    """
    driver.get(MESSAGES_PAGE)
    time.sleep(2)

    scroll_conversations(driver)

    conversations = driver.find_elements(By.CLASS_NAME, CONVERSATION_CLASS)

    for i, conversation in enumerate(conversations):
        try:
            conversation.click()
            time.sleep(1)

            extract_images_and_videos(driver, save_dir)

        except Exception as e:
            print(f"[conversation {i}] failed: {e}")
            continue


@tool("save_image")
@retry()
def save_image(url, file_path):
    """
    Download and save an image from a URL.

    Args:
        url (str): Direct image URL.
        file_path (str): Local file path to save the image.

    Behavior:
        - Performs HTTP GET request
        - Writes binary content to disk
    """
    r = requests.get(url, timeout=10)
    r.raise_for_status()

    with open(file_path, 'wb') as f:
        f.write(r.content)


@tool("save_video")
@retry()
def save_video(url, file_path):
    """
    Download and save a video from a URL.

    Args:
        url (str): Direct video URL.
        file_path (str): Local file path to save the video.

    Behavior:
        - Performs HTTP GET request
        - Writes binary content to disk
    """
    r = requests.get(url, timeout=10)
    r.raise_for_status()

    with open(file_path, 'wb') as f:
        f.write(r.content)


@tool("get_OF_cookies")
@retry()
def get_OF_cookies(email=None, password=None):
    """
    Retrieve authentication cookies for an OnlyFans session.

    Args:
        email (str, optional): Account email.
        password (str, optional): Account password.

    Returns:
        list: Selenium cookie objects representing authenticated session.

    Use when:
        - You need authenticated HTTP requests outside Selenium
    """
    driver = login_to_onlyfans(email, password)

    cookies = driver.get_cookies()
    driver.quit()

    return cookies


# ======================
# TOOL REGISTRY
# ======================
ONLYFANS_TOOLS = [
    extract_media,
    extract_images_and_videos,
    scroll_conversations,
    scroll_messages,
    save_image,
    save_video,
    login_to_onlyfans,
    get_OF_cookies
]