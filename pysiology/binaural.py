from ipykernel.comm import Comm
import os
import nb_assets

binaural_comm = None

def open_binaural_comm():
    global binaural_comm
    binaural_comm = Comm(target_name='binauralComm',
                    target_module='binaural', data={})
def install_javascript():
    assets = [("coffeescript", "binaural.coffee"),
            ]
    path = os.path.dirname(os.path.abspath(__file__))
    nb_assets.display_assets(assets, input_dir=os.path.join(path,"assets"), output_dir=os.path.join("static"))
    open_binaural_comm()


def binaural_set(left=100,right=100, gain_left=0, gain_right=0, duration=None):
    msg = dict(command="set",
               left=left,
               right=right,
               gain_left=gain_left,
               gain_right=gain_right,
               duration=duration)
    global binaural_comm
    binaural_comm.send(msg)

def binaural_stop():
    global binaural_comm
    binaural_comm.send(dict(command="stop"))    
