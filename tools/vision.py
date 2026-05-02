from qwen_agent.tools.base import register_tool, BaseTool

@register_tool('vis_desc_img')
class DescribeImageTool(BaseTool):
    """Sends an image to the vision model for analysis after encoding as Base64"""

    description = 'Converts an image to Base64, then sends it to the vision model to be analyzed and converted into a text description.'
    
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'An absolute filepath or a direct URL to an image.'},
            'prompt': {'type': 'string', 'description': 'A prompt that summarizes what the user wants from the vision model output. e.g. "Describe what is happening in this photo."'}
        },
        'required': ['path'],
    }

    def call(self, params: str, **kwargs):
        import base64
        import requests
        import os
        import json5

        p = json5.loads(params)
        path = p['path']
        prompt = p['prompt']

        VISION_URL = "http://localhost:14530/v1/chat/completions"
        # Note: using complete second-state model with bundled vision

        def encode_image(file_path):
            with open(file_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')

        def get_mime_type(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            return {
                ".jpg": "jpeg",
                ".jpeg": "jpeg",
                ".png": "png",
                ".webp": "webp"
            }.get(ext, "jpeg")  # fallback

        # Handle URL vs local file
        if path.startswith("http"):
            image_url = path
        else:
            encoded_image = encode_image(path)
            mime = get_mime_type(path)
            image_url = f"data:image/{mime};base64,{encoded_image}"

        payload = {
            "model": "llava-v1.5-7b-Q4_K_M-complete.gguf",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        },
                        {"type": "text", "text": prompt if prompt else "Describe this image in detail."}
                    ]
                }
            ],
            "max_tokens": 300
        }

        res = requests.post(VISION_URL, json=payload, timeout=60)

        return res.json()