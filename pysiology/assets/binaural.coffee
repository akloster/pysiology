define('binaural', [], ()->
    class BinauralBeat
        constructor: (@left,@right,@gainLeft, @gainRight, @duration)->
            audioCtx = window.binauralAudioCtx
            @audioCtx = audioCtx
            # Nodes
            # oscillator1 -> gain1 -> merger
            # oscillator2 -> gain2 -> merger
            #
            console.log("duration", @duration)
            oscillator1 = audioCtx.createOscillator()
            oscillator1.frequency.value = @left
            gain1 = audioCtx.createGain()
            gain1.gain.value = @gainLeft
            oscillator1.connect(gain1)
            merger = audioCtx.createChannelMerger(2)
            silence = audioCtx.createBufferSource()
            silence.connect(merger, 0, 0)
            gain1.connect(merger,0,0)
            oscillator2 = audioCtx.createOscillator()
            oscillator2.frequency.value = @right
            gain2 = audioCtx.createGain()
            gain2.gain.value = @gainRight
            oscillator2.connect(gain2)
            gain2.connect(merger,0,1)
            merger.connect(audioCtx.destination)
            oscillator1.start(0)
            oscillator2.start(0)
            @oscillator1 = oscillator1
            @oscillator2 = oscillator2
            if @duration?
              stopTime = audioCtx.currentTime + @duration
              console.log stopTime
              @oscillator1.stop(stopTime)
              @oscillator2.stop(stopTime)
              window.binauralBeatSingleton = undefined
            @gainNode1 = gain1
            @gainNode2 = gain2

        change: (left, right, gainLeft, gainRight, duration)->
            console.log "Tone changing ..."
            @left = left
            @right = right
            @gainLeft = gainLeft
            @gainRight = gainRight
            @oscillator1.frequency.value = left
            @oscillator2.frequency.value = right
            @gainNode1.gain.value = gainLeft
            @gainNode2.gain.value = gainRight
            @duration = duration
            if duration?
              stopTime = @audioCtx.currentTime + @duration
              console.log stopTime
              @oscillator1.stop(stopTime)
              @oscillator2.stop(stopTime)
              window.binauralBeatSingleton = undefined
        stop: ()->
            # After stopping the source nodes, the whole tree is discarded by
            # webaudio
            @oscillator1.stop()
            @oscillator2.stop()
    console.log "Loading Binaural Module"
    unless window.binauralAudioCtx
        window.binauralAudioCtx = new AudioContext()
    window.binauralBeatSingleton = undefined
    binauralComm = (comm, msg)->
        console.log('Starting Comm für binaural beats via web audio', comm, msg)
        comm.on_msg((m)->
            data = m.content.data
            window.message = m
            switch data.command
                when "set" then binauralSet(data)
                when "stop" then binauralStop(data)
        )
        comm.on_close((m)->
                console.log('close', m)
                )
    binauralSet = (data)->
        if window.binauralBeatSingleton?
           binauralBeatSingleton.change(data.left, data.right, data.gain_left, data.gain_right, data.duration)
        else
           window.binauralBeatSingleton = new BinauralBeat(data.left, data.right, data.gain_left, data.gain_right, data.duration)
    binauralStop = (data)->
        binauralBeatSingleton?.stop()
        window.binauralBeatSingleton = undefined

    return {'binauralComm': binauralComm}
)
