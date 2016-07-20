Pysiology
=============

Pysiology will be a framework for physiological experiments and their analysis.

It is still in a rough state, and only supports the Neurosky Mindwave Mobile headest, which can record EEG signals.

I decided to publish this to Github, despite its rough state, to give listeners of my "Brainwaves for Hackers 2.0" talk at EuroPython 2.0 something to look at after wondering how that all worked.

Please do not use this package for treatment purposes, and only use this on yourself or others if you understand the medical and legal implications on an expert level!

Status:
======

* Pysiology now uses the Jupyter kernel's Tornado loop to handle a 
  websocket connection to the streaming server.
* Experiments use Metaclasses to define devices
* Mindwave and Bitalino devices are implemented
* Bitalino can stream, but data parsing is seriously broken... working on
  incorporating manufacturer's code
* Notebook code now uses a comm channel to update bokeh plots
