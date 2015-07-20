requirejs.undef("asyncio")
define("asyncio", ["jquery", "widgets/js/widget"], ($, widget)->
  AsyncioTaskWidgetView = widget.DOMWidgetView.extend({
    render: ->
      AsyncioTaskWidgetView.__super__.render.apply(this, arguments)
      html = $("<p><button class='btn btn-danger asyncio-stop-task'>stop</button> </p>")
      this.setElement(html)
      el = this.el
      $el = $(el)
      $el.find(".asyncio-stop-task").click =>
        this.send({'msg_type':'stop_task'})
      @model.on('msg:custom', (msg)=> @handle_custom_message(msg))
    handle_custom_message: (msg)->
      if msg.msg_type == 'task_stopped'
        $(@el).find(".asyncio-stop-task").attr("disabled", true)
  })
  BokehAnimationWidget =  widget.DOMWidgetView.extend(
        render: ()->
            html = $("<p>Bokeh Animation Manager</p>")
            this.setElement(html)
            this.model.on('msg:custom', $.proxy(this.handle_custom_message, this))
        handle_custom_message: (data)->
            switch
                when (data.custom_type == "replace_bokeh_data_source")
                    ds = Bokeh.Collections(data.ds_model).get(data.ds_id)
                    ds.set($.parseJSON(data.ds_json))
                    ds.trigger("change")
    )
  return {
    AsyncioTaskWidgetView: AsyncioTaskWidgetView
    BokehAnimationWidget: BokehAnimationWidget
  }
)
