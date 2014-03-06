define([
    'q', 
    'knockout',
    'viewmodel/base',
    'util/postOffice',
    'util/form',
    'store/ProviderTypes',
    'store/Accounts',
    'store/Profiles',
    'store/AccountSecurityGroups',
    'api/api'
],
function (Q, ko, $galaxy, formutils, ProviderTypeStore, AccountStore, ProfileStore, AccountSecurityGroupStore, API) {
    var vm = function () {
        var self = this;

        /*
         *  ==================================================================================
         *   V I E W   V A R I A B L E S
         *  ==================================================================================
         */
        self.selectedAccount = ko.observable(null);
        self.selectedProviderType = ko.observable(null);
        self.accountTitle = ko.observable(null);
        self.saveAction = self.createAccount;
        self.DefaultGroupStore = ko.observableArray();

        self.ProviderTypeStore = ProviderTypeStore;
        self.AccountStore = AccountStore;
        self.ProfileStore = ProfileStore;
        self.AccountSecurityGroupStore = AccountSecurityGroupStore;


        /*
         *  ==================================================================================
         *   R E G I S T R A T I O N   S E C T I O N
         *  ==================================================================================
         */
        self.id = 'account.securitygroup';
        self.templatePath = 'securityGroups.html';
        self.domBindingId = '#account-securitygroup';

        try {
            $galaxy.join(self);
        } catch (ex) {
            console.log(ex);            
        }


        /*
         *  ==================================================================================
         *   E V E N T   S U B S C R I P T I O N S
         *  ==================================================================================
         */
        self.$66.news.subscribe('account.securitygroup.rendered', function (data) {

            ProviderTypeStore.populate().then(function () {
                return AccountStore.populate();
            }).then(function () {
                return ProfileStore.populate();
            }).then(function () {
                self.init(data);
            });
        });


        /*
         *  ==================================================================================
         *   V I E W   M E T H O D S
         *  ==================================================================================
         */

        self.init = function (data) {
            var account = null;
            var provider_type = null;

            self.DefaultGroupStore.removeAll();

            if (data.hasOwnProperty('account')) {
                account = AccountStore.collection().filter(function (a) {
                    return a.id === parseInt(data.account, 10);
                })[0];

                self.accountTitle(account.title);
                self.selectedAccount(account);

                API.SecurityGroups.loadByAccount(account).then(function (data) {
                    console.log(data);

                    for (var group in data.provider_groups) {
                        self.AccountSecurityGroupStore.add(data.provider_groups[group]);
                    }

                    for (group in data.results) {
                        if (data.results[group].is_default) {
                            self.DefaultGroupStore.push(data.results[group]);
                        }
                    }

                    console.log('self.DefaultGroupStore',self.DefaultGroupStore());

                    self.listDefaultGroups();
                });
            }
        };

        self.saveSecurityGroups = function (model, evt) {
        };

        self.cancelChanges = function (model, evt) {
            $galaxy.transport({ view: 'account.list' });
        };

        self.capture = function (model, evt) {
            if (evt.charCode === 13) {
                self.addDefaultSecurityGroup(document.getElementById('new_securitygroup_name').value);
                return false;
            }
            return true;
        };

        self.captureNewGroup = function (model, evt) {
            if (evt.charCode === 13) {
                self.addSecurityGroup(document.getElementById('securitygroup_name').value);
                return false;
            }
            return true;
        };

        self.addDefaultSecurityGroup = function (name, evt) {
            var record = {};
            record.name = name;
            record.cloud_provider = self.selectedAccount().id;
            record.is_default = true;
            record.description = "";

            API.SecurityGroups.save(record).then(function (newGroup) {
                formutils.clearForm('default-securitygroup-form');
                self.DefaultGroupStore.push(newGroup);
                self.listDefaultGroups();
            })
            .catch(function (error) {
                console.error(error);
            }).done();
        };

        self.deleteDefaultSecurityGroup = function (groupId) {
            console.log('group to delete', groupId);
            var record = _.findWhere(self.DefaultGroupStore(), { id: parseInt(groupId, 10) });
            console.log('found record', record);

            if (typeof record !== 'undefined') {
                record.is_default = false;

                API.SecurityGroups.updateDefault(record).then(function () {
                    self.listDefaultGroups();
                })
                .catch(function (error) {
                    record.is_default = true;
                    console.error(error);
                }).done();
            }
        };

        self.listDefaultGroups = function () {
            var account = self.selectedAccount();

            $('#default_group_list').empty();

            // For each security group that is default, add a label styled span element in the UI
            _.each(self.DefaultGroupStore(), function (g) {
                if (g.is_default && g.provider_id === account.id) {
                    $('#default_group_list').append('<span id="defaultgroup_'+ g.id +'" style="cursor: pointer; margin: 0 5px;" defaultlabel class="label label-success"><span class="iconic-x"></span> '+ g.name +'</span>');
                }
            });

            // Handle the user clicking on the group label to set the group to is_default:false
            $('span[defaultlabel]').click(function (evt) {
                var groupId = evt.target.id.split('_')[1];
                self.deleteDefaultSecurityGroup(groupId);
            });
        };

        self.setForAccount = function (account) {
            if (!account.hasOwnProperty('security_group') || !account.hasOwnProperty('yaml')) {
                var accountsLength = stores.Accounts().length;
                var account = stores.Accounts()[accountsLength - 1];
            }
            self.selectedAccount(account);

            API.SecurityGroups.loadByAccount(account)
                .then(function () {
                    $('#stackdio_security_group').selectpicker();
                    
                    self.listDefaultGroups();
                });
            self.showDefaultGroupForm();
        };


    };

    vm.prototype = new base();
    return new vm();
});
