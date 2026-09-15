//Patch in Old function of backbone view.
Backbone.View = (function (View) {
    "use strict";
    return View.extend({
        constructor: function (options) {
            this.options = options || {};
            View.apply(this, arguments);
        }
    });
}(Backbone.View));

//Patch Collection Reset for now .....
Backbone.Collection = (function (Collection) {
    "use strict";
    var wrapError = function (model, options) {
        var error = options.error;
        options.error = function (resp) {
            if (error) {error(model, resp, options);}
            model.trigger('error', model, resp, options);
        };
    };
    return Collection.extend({
        fetch: function (options) {
            options = options ? _.clone(options) : {};
            if (options.parse === undefined) {options.parse = true;}
            var success = options.success, collection = this;
            options.success = function (resp) {
                var method = options.update ? 'set' : 'reset';
                collection[method](resp, options);

                if (success){ success(collection, resp, options);}
                collection.trigger('sync', collection, resp, options);
            };
            wrapError(this, options);
            return this.sync('read', this, options);
        },
        //Added back in for now...Should probably make the jump to set in the future.
        update: function(models, options) {
            return this.set(models, options);
        }
    });
}(Backbone.Collection));