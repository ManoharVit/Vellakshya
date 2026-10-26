"""
Vellakshya PDF Workstation — Hugging Face Space & FastAPI Entrypoint.
Architect & Lead Developer: Giri Manohar Vemula
LinkedIn: https://www.linkedin.com/in/manoharv511
GitHub: https://github.com/ManoharVit
"""
import os

# Disable Gradio SSR mode to avoid secondary port conflicts
os.environ["GRADIO_SSR_MODE"] = "False"

import gradio as gr
from app.main import app

with gr.Blocks(
    title="Vellakshya PDF Workstation",
    fill_height=True,
    css="""
    footer { visibility: hidden !important; display: none !important; }
    .gradio-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }
    #vellakshya-frame { width: 100%; height: 96vh; border: none; overflow: auto; display: block; }
    """
) as demo:
    gr.HTML(
        """
        <iframe id="vellakshya-frame" src="/" title="Vellakshya PDF Workstation" style="width:100%; height:96vh; border:none;"></iframe>
        """
    )

app = gr.mount_gradio_app(app, demo, path="/gradio", ssr_mode=False)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
