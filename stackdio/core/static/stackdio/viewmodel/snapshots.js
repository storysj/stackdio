define(["knockout",
        "util/form",
        "viewmodel/abstract",
        "model/models",
        "store/stores",
        "api/api"], 
    function (ko, formutils, abstractVM, models, stores, API) {

        var vm = function () {
            var self = this;

            self.userCanModify = ko.observable();
            self.osChoices = [
                {
                    id: 'ext2',
                    title: 'ext2'
                },
                {
                    id: 'ext3',
                    title: 'ext3'
                },
                {
                    id: 'ext4',
                    title: 'ext4'
                },
                {
                    id: 'fuse',
                    title: 'fuse'
                },
                {
                    id: 'xfs',
                    title: 'xfs'
                }
            ];

            // Query OPTIONS on /providers and if DELETE is not in allowed verb list, user is not admin
            API.Snapshots.options()
                .then(function (allowed) {
                    self.userCanModify(allowed.verbs.indexOf('DELETE') !== -1);
                });

            self.addSnapshot = function (model, evt) {
                var record = formutils.collectFormFields(evt.target.form);
                record.account = self.selectedAccount;

                console.log('record',record);

                API.Snapshots.save(record)
                    .then(function () {
                        $("#snapshot-form-container").dialog("close");
                        self.showSuccess();
                    })
                    .catch(function (error) {
                        $("#alert-error").show();
                    });
            };

            self.removeSnapshot = function (snapshot) {
                API.Snapshots.delete(snapshot)
                    .then(self.showSuccess)
                    .catch(function (error) {
                        $("#alert-error").show();
                    });
            };

            self.showSnapshotForm = function (account) {
                self.selectedAccount = account;
                $( "#snapshot-form-container" ).dialog("open");
            };

            self.closeSnapshotForm = function () {
                $( "#snapshot-form-container" ).dialog("close");
            };

            /*
             *  ==================================================================================
             *  D I A L O G   E L E M E N T S
             *  ==================================================================================
             */
            $("#snapshot-form-container").dialog({
                autoOpen: false,
                width: 550,
                modal: false
            });
        };

        vm.prototype = new abstractVM();

        return vm;
});