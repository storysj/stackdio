Ext.define('stackdio.model.Snapshot', {
    extend: 'Ext.data.Model'

    ,fields: [
         { name: 'id',              type: 'int' }
        ,{ name: 'url',             type: 'string' }
        ,{ name: 'title',           type: 'string' }
        ,{ name: 'description',     type: 'string' }
        ,{ name: 'cloud_provider',  type: 'int' }
        ,{ name: 'size_in_gb',      type: 'float' }
        ,{ name: 'snapshot_id',     type: 'string' }
    ]


    ,proxy: {
        type: 'rest',
        url: Settings.api_url + '/api/snapshots/',
        reader: {
            type: 'json',
            root: 'results'
        },
        headers: {
            "Authorization": "Basic " + Base64.encode('testuser:password')
        },
        pageParam: undefined,
        limitParam: undefined,
        startParam: undefined
    }
});