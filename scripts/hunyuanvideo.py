import time
import torch
import gradio as gr
import diffusers
from modules import scripts, processing, shared, images, devices, sd_models, sd_checkpoint, model_quant


repo_id = 'tencent/HunyuanVideo'
"""
prompt_template = { # default
    "template": (
        "<|start_header_id|>system<|end_header_id|>\n\nDescribe the video by detailing the following aspects: "
        "1. The main content and theme of the video."
        "2. The color, shape, size, texture, quantity, text, and spatial relationships of the contents, including objects, people, and anything else."
        "3. Actions, events, behaviors temporal relationships, physical movement changes of the contents."
        "4. Background environment, light, style, atmosphere, and qualities."
        "5. Camera angles, movements, and transitions used in the video."
        "6. Thematic and aesthetic concepts associated with the scene, i.e. realistic, futuristic, fairy tale, etc<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n{}<|eot_id|>"
    ),
    "crop_start": 95,
}
"""


class Script(scripts.Script):
    def title(self):
        return 'Video: Hunyuan Video'

    def show(self, is_img2img):
        return not is_img2img if shared.native else False

    # return signature is array of gradio components
    def ui(self, _is_img2img):
        def video_type_change(video_type):
            return [
                gr.update(visible=video_type != 'None'),
                gr.update(visible=video_type == 'GIF' or video_type == 'PNG'),
                gr.update(visible=video_type == 'MP4'),
                gr.update(visible=video_type == 'MP4'),
            ]

        with gr.Row():
            gr.HTML('<a href="https://huggingface.co/tencent/HunyuanVideo">&nbsp Hunyuan Video</a><br>')
        with gr.Row():
            num_frames = gr.Slider(label='Frames', minimum=9, maximum=257, step=1, value=45)
        with gr.Row():
            video_type = gr.Dropdown(label='Video file', choices=['None', 'GIF', 'PNG', 'MP4'], value='None')
            duration = gr.Slider(label='Duration', minimum=0.25, maximum=10, step=0.25, value=2, visible=False)
        with gr.Row():
            gif_loop = gr.Checkbox(label='Loop', value=True, visible=False)
            mp4_pad = gr.Slider(label='Pad frames', minimum=0, maximum=24, step=1, value=1, visible=False)
            mp4_interpolate = gr.Slider(label='Interpolate frames', minimum=0, maximum=24, step=1, value=0, visible=False)
        video_type.change(fn=video_type_change, inputs=[video_type], outputs=[duration, gif_loop, mp4_pad, mp4_interpolate])
        return [num_frames, video_type, duration, gif_loop, mp4_pad, mp4_interpolate]

    def run(self, p: processing.StableDiffusionProcessing, num_frames, video_type, duration, gif_loop, mp4_pad, mp4_interpolate): # pylint: disable=arguments-differ, unused-argument
        # set params
        num_frames = int(num_frames)
        p.width = 32 * int(p.width // 32)
        p.height = 32 * int(p.height // 32)
        p.task_args['output_type'] = 'pil'
        p.task_args['generator'] = torch.manual_seed(p.seed)
        p.task_args['num_frames'] = num_frames
        # p.task_args['prompt_template'] = prompt_template
        p.sampler_name = 'Default'
        p.do_not_save_grid = True
        p.ops.append('video')

        # load model
        cls = diffusers.HunyuanVideoPipeline
        if shared.sd_model.__class__ != cls:
            sd_models.unload_model_weights()
            kwargs = {}
            kwargs = model_quant.create_bnb_config(kwargs)
            kwargs = model_quant.create_ao_config(kwargs)
            transformer = diffusers.HunyuanVideoTransformer3DModel.from_pretrained(
                repo_id,
                subfolder="transformer",
                torch_dtype=devices.dtype,
                revision="refs/pr/18",
                cache_dir = shared.opts.hfcache_dir,
                **kwargs
            )
            shared.sd_model = cls.from_pretrained(
                repo_id,
                transformer=transformer,
                revision="refs/pr/18",
                cache_dir = shared.opts.hfcache_dir,
                torch_dtype=devices.dtype,
                **kwargs
            )
            shared.sd_model.scheduler._shift = 7.0 # pylint: disable=protected-access
            sd_models.set_diffuser_options(shared.sd_model)
            shared.sd_model.sd_checkpoint_info = sd_checkpoint.CheckpointInfo(repo_id)
            shared.sd_model.sd_model_hash = None
        shared.sd_model = sd_models.apply_balanced_offload(shared.sd_model)
        shared.sd_model.vae.enable_slicing()
        shared.sd_model.vae.enable_tiling()
        devices.torch_gc(force=True)
        shared.log.debug(f'Video: cls={shared.sd_model.__class__.__name__} args={p.task_args}')

        # run processing
        t0 = time.time()
        processed = processing.process_images(p)
        t1 = time.time()
        if processed is not None and len(processed.images) > 0:
            shared.log.info(f'Video: frames={len(processed.images)} time={t1-t0:.2f}')
            if video_type != 'None':
                images.save_video(p, filename=None, images=processed.images, video_type=video_type, duration=duration, loop=gif_loop, pad=mp4_pad, interpolate=mp4_interpolate)
        return processed