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

import json5
from qwen_agent.tools.base import BaseTool, register_tool
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

@register_tool('of_scroll_convos')
class ScrollConversationsTool(BaseTool):
    description = 'Scroll the OnlyFans conversations sidebar until all conversations are loaded.'
    parameters = {'type': 'object', 'properties': {}, 'required': []}

    @retry()
    def call(self, params: str, **kwargs) -> dict:
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


@register_tool('of_scroll_msgs')
class ScrollMessagesTool(BaseTool):
    description = 'Scroll the current conversation to load additional messages.'
    parameters = {'type': 'object', 'properties': {}, 'required': []}

    @retry()
    def call(self, params: str, **kwargs) -> dict:
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


@register_tool('of_save_media')
class SaveMediaTool(BaseTool):
    description = 'Download and save a media file from a URL to disk.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Direct media URL.'},
            'file_path': {'type': 'string', 'description': 'Local path to save to.'},
        },
        'required': ['url', 'file_path'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p['url']
        file_path = p['file_path']
        if not url.startswith(("http://", "https://")):
            return tool_result(error="url must start with http:// or https://")
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(r.content)
            return tool_result(data={"url": url, "file_path": file_path, "bytes": len(r.content)})
        except Exception as e:
            return tool_result(error=str(e))


@register_tool('of_extract_all')
class ExtractImagesAndVideosTool(BaseTool):
    description = 'Extract all images and videos from the currently open OnlyFans conversation.'
    parameters = {
        'type': 'object',
        'properties': {
            'save_dir': {'type': 'string', 'description': 'Directory path where media files will be saved. Created if it does not exist.'},
        },
        'required': ['save_dir'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        save_dir = p['save_dir']
        try:
            driver = _get_driver()
            os.makedirs(save_dir, exist_ok=True)
            images_saved = 0
            videos_saved = 0
            scroll_tool = ScrollMessagesTool()
            save_tool = SaveMediaTool()

            while True:
                scroll_tool.call('{}')
                messages = driver.find_elements(By.CLASS_NAME, MESSAGE_CLASS)
                for msg_i, message in enumerate(messages):
                    try:
                        media_wrapper = safe_find(message, By.CLASS_NAME, MEDIA_WRAPPER_CLASS)
                        if not media_wrapper:
                            continue
                        for i, img in enumerate(media_wrapper.find_elements(By.CLASS_NAME, IMAGE_CLASS)):
                            src = img.get_attribute("src")
                            if src:
                                save_tool.call(json5.dumps({"url": src, "file_path": f"{save_dir}/image_{msg_i}_{i}.jpg"}))
                                images_saved += 1
                        for i, video in enumerate(media_wrapper.find_elements(By.CLASS_NAME, VIDEO_CLASS)):
                            for j, source in enumerate(video.find_elements(By.TAG_NAME, "source")):
                                src = source.get_attribute(SOURCE_ATTRIBUTE)
                                if src:
                                    save_tool.call(json5.dumps({"url": src, "file_path": f"{save_dir}/video_{msg_i}_{i}_{j}.mp4"}))
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


@register_tool('of_extract')
class ExtractMediaTool(BaseTool):
    description = 'Extract media from ALL conversations in the user\'s OnlyFans inbox.'
    parameters = {
        'type': 'object',
        'properties': {
            'save_dir': {'type': 'string', 'description': 'Directory to store downloaded media. Created if it does not exist.'},
        },
        'required': ['save_dir'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        save_dir = p['save_dir']
        try:
            driver = _get_driver()
            os.makedirs(save_dir, exist_ok=True)
            driver.get(MESSAGES_PAGE)
            time.sleep(2)
            ScrollConversationsTool().call('{}')
            conversations = driver.find_elements(By.CLASS_NAME, CONVERSATION_CLASS)
            processed = 0
            failed = 0
            extract_tool = ExtractImagesAndVideosTool()
            for i, conversation in enumerate(conversations):
                try:
                    conversation.click()
                    time.sleep(1)
                    extract_tool.call(json5.dumps({"save_dir": save_dir}))
                    processed += 1
                except Exception:
                    failed += 1
                    continue
            return tool_result(data={"save_dir": save_dir, "conversations_processed": processed, "conversations_failed": failed})
        except Exception as e:
            return tool_result(error=str(e))
