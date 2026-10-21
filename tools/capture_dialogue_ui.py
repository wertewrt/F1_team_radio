"""Capture live dialogue UI using the current portable sample configuration."""
from pathlib import Path
import sys,json,tkinter as tk
from PIL import ImageGrab
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from teamradio.gui import TeamRadioApp,_enable_high_dpi
_enable_high_dpi()
root=tk.Tk();app=TeamRadioApp(root)
root.geometry('1580x1080+100+100');root.attributes('-topmost',True)
app.read_config(ROOT/'examples/dialogue_scroll.json')
messages=json.loads((ROOT/'examples/dialogue_messages.json').read_text(encoding='utf-8'))
def capture(widget,name):
    widget.update()
    x,y=widget.winfo_rootx(),widget.winfo_rooty()
    ImageGrab.grab(bbox=(x,y,x+widget.winfo_width(),y+widget.winfo_height())).save(ROOT/'examples'/name)
def ready(attempt=0):
    if app._analyzing:
        if attempt>200: app.close();raise RuntimeError('Audio preview timed out')
        root.after(50,lambda:ready(attempt+1));return
    if app.analyzer is None: app.close();raise RuntimeError('Sample audio did not load')
    app.timeline.set(app.audio_start+messages[1]['start']+.65)
    app._render_preview();app.settings_canvas.yview_moveto(.68)
    root.after(300,stage_one)
def stage_one():
    capture(root,'dialogue_studio_ui.png')
    editor=app.open_dialogue_editor();editor.geometry('1100x940+200+100')
    editor.attributes('-topmost',True)
    editor.tree.selection_set('1');editor._selected()
    root.after(300,lambda:stage_two(editor))
def stage_two(editor):
    capture(editor,'dialogue_editor_ui.png')
    print('Live dialogue UI and editor screenshots refreshed with aligned sample audio')
    app.close()
root.after(50,ready)
root.mainloop()
