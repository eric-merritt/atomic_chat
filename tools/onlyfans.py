"""OnlyFans media extraction tools.

WARNING: These tools require an active authenticated session created from
pre-obtained cookies. DO NOT pass raw credentials (email/password) to any tool.
"""

import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from langchain.tools import tool
from tools._output import tool_result, retry

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
# MODULE-LEVEL DRIVER
# ======================
_active_driver: webdriver.Firefox | None = None


def _get_driver() -> webdriver.Firefox:
    """Get the active driver session. Raises if not initialized."""
    if _active_driver is None:
        raise RuntimeError(
            "No active OnlyFans session. Call _create_driver_from_cookies() first."
        )
    return _active_driver


def _create_driver_from_cookies(cookies: list[dict], geckodriver_path: str = "") -> webdriver.Firefox:
    """Create an authenticated Firefox driver from pre-obtained cookies.

    DO NOT pass raw credentials to this function.
    Cookies should be obtained manually or from a secure credential store.

    Args:
        cookies: List of cookie dicts with keys: name, value, domain, path.
        geckodriver_path: Path to geckodriver binary. Auto-detected if empty.
    """
    global _active_driver

    if not geckodriver_path:
        geckodriver_path = os.environ.get("GECKODRIVER_PATH", "/home/ermer/.local/bin/geckodriver")

    firefox_options = Options()
    firefox_options.accept_insecure_certs = True

    service = Service(geckodriver_path)
    driver = webdriver.Firefox(service=service, options=firefox_options)

    driver.get("https://onlyfans.com")
    time.sleep(2)

    for cookie in cookies:
        driver.add_cookie(cookie)

    driver.get(MESSAGES_PAGE)
    time.sleep(2)

    _active_driver = driver
    return driver


# ======================
# HELPERS
# ======================
def safe_find(element, by, value):
    try:
        return element.find_element(by, value)
    except Exception:
        return None


# ======================
# TOOLS
# ======================

@tool("scroll_conversations")
@retry()
def scroll_conversations() -> str:
    """Scroll the OnlyFans conversations sidebar until all conversations are loaded.

    WHEN TO USE: Before iterating through conversations to ensure all are loaded.
    WHEN NOT TO USE: When you only need the currently visible conversations.

    REQUIRES: An active OnlyFans session (set up before calling this tool).
    SIDE EFFECT: Modifies the scroll position of the conversation sidebar in the browser.

    WARNING: DO NOT pass raw credentials (email/password) to any tool.
    Use pre-obtained session cookies for authentication.

    Output format:
        {"status": "success", "data": {"message": "Scrolled to end of conversations"}, "error": ""}
    """
    try:
        driver = _get_driver()
        scroller = driver.find_element(By.CLASS_NAME, SCROLLER_CLASS)
        last_height = 0
        while True:
            driver.execute_script(
                "arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroller
            )
            time.sleep(2)
            new_height = scroller.size["height"]
            if new_height == last_height:
                break
            last_height = new_height
        return tool_result(data={"message": "Scrolled to end of conversations"})
    except Exception as e:
        return tool_result(error=str(e))


@tool("scroll_messages")
@retry()
def scroll_messages() -> str:
    """Scroll the current conversation to load additional messages.

    WHEN TO USE: When you need to load older messages in the current conversation.
    WHEN NOT TO USE: When you are not inside a conversation view.

    REQUIRES: An active OnlyFans session with a conversation open.
    SIDE EFFECT: Scrolls the message container, triggering lazy loading of older messages.

    WARNING: DO NOT pass raw credentials (email/password) to any tool.

    Output format:
        {"status": "success", "data": {"message": "Scrolled message container"}, "error": ""}
    """
    try:
        driver = _get_driver()
        scroller = driver.find_element(By.CLASS_NAME, SCROLLER_CLASS)
        driver.execute_script(
            "arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroller
        )
        time.sleep(2)
        return tool_result(data={"message": "Scrolled message container"})
    except Exception as e:
        return tool_result(error=str(e))


@tool("save_image")
@retry()
def save_image(url: str, file_path: str) -> str:
    """Download and save an image from a URL to disk.

    WHEN TO USE: When you have a direct image URL to download.
    WHEN NOT TO USE: When you need to find image URLs first (use extract_images_and_videos).

    WARNING: This WRITES a file to disk. Verify the save path before calling.

    Args:
        url: Direct image URL. Must start with http:// or https://.
        file_path: Local file path to save the image to.

    Output format:
        {"status": "success", "data": {"url": "...", "file_path": "...", "bytes": N}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(r.content)
        return tool_result(data={"url": url, "file_path": file_path, "bytes": len(r.content)})
    except Exception as e:
        return tool_result(error=str(e))


@tool("save_video")
@retry()
def save_video(url: str, file_path: str) -> str:
    """Download and save a video from a URL to disk.

    WHEN TO USE: When you have a direct video URL to download.
    WHEN NOT TO USE: When you need to find video URLs first (use extract_images_and_videos).

    WARNING: This WRITES a file to disk. Verify the save path before calling.

    Args:
        url: Direct video URL. Must start with http:// or https://.
        file_path: Local file path to save the video to.

    Output format:
        {"status": "success", "data": {"url": "...", "file_path": "...", "bytes": N}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(r.content)
        return tool_result(data={"url": url, "file_path": file_path, "bytes": len(r.content)})
    except Exception as e:
        return tool_result(error=str(e))


@tool("extract_images_and_videos")
@retry()
def extract_images_and_videos(save_dir: str) -> str:
    """Extract all images and videos from the currently open conversation.

    WHEN TO USE: When inside a conversation and you want to download all media.
    WHEN NOT TO USE: When you want to extract from ALL conversations (use extract_media).

    REQUIRES: An active OnlyFans session with a conversation open.
    SIDE EFFECT: Downloads files to save_dir. Scrolls the conversation to load all messages.

    WARNING: DO NOT pass raw credentials. This tool writes multiple files to disk.

    Args:
        save_dir: Directory path where media files will be saved. Created if it does not exist.

    Output format:
        {"status": "success", "data": {"save_dir": "...", "images_saved": N, "videos_saved": N}, "error": ""}
    """
    try:
        driver = _get_driver()
        os.makedirs(save_dir, exist_ok=True)
        images_saved = 0
        videos_saved = 0

        while True:
            scroll_messages.invoke({})
            messages = driver.find_elements(By.CLASS_NAME, MESSAGE_CLASS)
            for msg_i, message in enumerate(messages):
                try:
                    media_wrapper = safe_find(message, By.CLASS_NAME, MEDIA_WRAPPER_CLASS)
                    if not media_wrapper:
                        continue
                    for i, img in enumerate(media_wrapper.find_elements(By.CLASS_NAME, IMAGE_CLASS)):
                        src = img.get_attribute("src")
                        if src:
                            save_image.invoke({"url": src, "file_path": f"{save_dir}/image_{msg_i}_{i}.jpg"})
                            images_saved += 1
                    for i, video in enumerate(media_wrapper.find_elements(By.CLASS_NAME, VIDEO_CLASS)):
                        for j, source in enumerate(video.find_elements(By.TAG_NAME, "source")):
                            src = source.get_attribute(SOURCE_ATTRIBUTE)
                            if src:
                                save_video.invoke({"url": src, "file_path": f"{save_dir}/video_{msg_i}_{i}_{j}.mp4"})
                                videos_saved += 1
                except Exception:
                    continue
            try:
                status = driver.find_element(By.CSS_SELECTOR, INFINITE_STATUS_PROMPT_CLASS)
                if "hidden" in status.get_attribute("class"):
                    break
            except Exception:
                break

        return tool_result(data={"save_dir": save_dir, "images_saved": images_saved, "videos_saved": videos_saved})
    except Exception as e:
        return tool_result(error=str(e))


@tool("extract_media")
@retry()
def extract_media(save_dir: str) -> str:
    """Extract media from ALL conversations in the user's OnlyFans inbox.

    WHEN TO USE: When you want to download all media from all conversations.
    WHEN NOT TO USE: When you only need media from the current conversation (use extract_images_and_videos).

    REQUIRES: An active OnlyFans session.
    SIDE EFFECT: Navigates through all conversations, downloads all media to save_dir.
    This is a long-running operation that clicks through every conversation.

    WARNING: DO NOT pass raw credentials. This tool writes many files to disk.

    Args:
        save_dir: Directory to store downloaded media. Created if it does not exist.

    Output format:
        {"status": "success", "data": {"save_dir": "...", "conversations_processed": N, "conversations_failed": N}, "error": ""}
    """
    try:
        driver = _get_driver()
        os.makedirs(save_dir, exist_ok=True)
        driver.get(MESSAGES_PAGE)
        time.sleep(2)
        scroll_conversations.invoke({})
        conversations = driver.find_elements(By.CLASS_NAME, CONVERSATION_CLASS)
        processed = 0
        failed = 0
        for i, conversation in enumerate(conversations):
            try:
                conversation.click()
                time.sleep(1)
                extract_images_and_videos.invoke({"save_dir": save_dir})
                processed += 1
            except Exception:
                failed += 1
                continue
        return tool_result(data={"save_dir": save_dir, "conversations_processed": processed, "conversations_failed": failed})
    except Exception as e:
        return tool_result(error=str(e))


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
]
