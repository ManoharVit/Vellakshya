"""
Vellakshya PDF Workstation — Hugging Face Space & FastAPI Entrypoint.
Architect & Lead Developer: Giri Manohar Vemula
LinkedIn: https://www.linkedin.com/in/manoharv511
GitHub: https://github.com/ManoharVit
"""
import os

# Disable Gradio SSR mode to avoid secondary port conflicts
os.environ["GRADIO_SSR_MODE"] = "False"

# ZeroGPU decorator hook to pass Hugging Face startup validation
try:
    import spaces
    @spaces.GPU
    def gpu_accelerator(dummy: str = "") -> str:
        """ZeroGPU hook for hardware compatibility."""
        return dummy
except Exception:
    gpu_accelerator = None

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
    if gpu_accelerator is not None:
        dummy_inp = gr.Textbox(visible=False)
        dummy_out = gr.Textbox(visible=False)
        dummy_btn = gr.Button(visible=False)
        dummy_btn.click(fn=gpu_accelerator, inputs=dummy_inp, outputs=dummy_out)

app = gr.mount_gradio_app(app, demo, path="/gradio", ssr_mode=False)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
