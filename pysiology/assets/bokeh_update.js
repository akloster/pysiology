// Generated by CoffeeScript 1.9.2
(function() {
  requirejs.undef('pysiology');

  define('pysiology', [], function() {
    var bokeh_update_target;
    bokeh_update_target = function(comm, msg) {
      var ds;
      console.log('Starting Bokeh Comm', comm, msg);
      comm.on_msg(function(m) {}, (function() {
        switch (false) {
          case !(data.custom_type === "replace_bokeh_data_source"):
            ds = Bokeh.Collections(data.ds_model).get(data.ds_id);
            ds.set($.parseJSON(data.ds_json));
            return ds.trigger("change");
        }
      })());
      return comm.on_close(function(m) {
        return console.log('close', m);
      });
    };
    return {
      'bokeh_update_target': bokeh_update_target
    };
  });

}).call(this);
