requirejs.undef('pysiology')
define('pysiology', [], ()->
        bokeh_update_target= (comm, msg)->
            console.log('Starting Bokeh Comm', comm, msg)
            comm.on_msg((m)->
                data = m.content.data
                switch
                    when (data.custom_type == "replace_bokeh_data_source")
                        ds = Bokeh.Collections(data.ds_model).get(data.ds_id)
                        ds.set($.parseJSON(data.ds_json))
                        ds.trigger("change")
                )
            comm.on_close((m)->
                    console.log('close', m)
                    )
        return {'bokeh_update_target': bokeh_update_target}
)

