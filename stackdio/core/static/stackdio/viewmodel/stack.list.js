define(['q', 'knockout', 'bootbox', 'util/galaxy', 'util/alerts', 'util/stack', 'store/Blueprints', 'store/Stacks', 'api/api'],
function (Q, ko, bootbox, $galaxy, alerts, stackutils, BlueprintStore, StackStore, API) {
    var vm = function () {
        var self = this;

        /*
         *  ==================================================================================
         *   V I E W   V A R I A B L E S
         *  ==================================================================================
        */
        self.stackActions = ['Stop', 'Terminate', 'Start', 'Launch', 'Delete', 'Provision'];
        self.stackHostActions = ['Stop', 'Terminate', 'Start'];
        self.selectedProfile = null;
        self.selectedAccount = null;
        self.selectedBlueprint = ko.observable({title:''});
        self.blueprintProperties = ko.observable();
        self.selectedStack = ko.observable();
        self.BlueprintStore = BlueprintStore;
        self.StackStore = StackStore;
        self.$galaxy = $galaxy;

        /*
         *  ==================================================================================
         *   R E G I S T R A T I O N   S E C T I O N
         *  ==================================================================================
        */
        self.id = 'stack.list';
        self.templatePath = 'stacks.html';
        self.domBindingId = '#stack-list';

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
        $galaxy.network.subscribe(self.id + '.docked', function (data) {
            StackStore.populate(true).catch(function (err) {
                console.error(err);
            });
            BlueprintStore.populate().then(function () {
                $('span').popover('hide');
            }).catch(function (err) {
                console.error(err);
            })
        });

        /*
         *  ==================================================================================
         *   V I E W   M E T H O D S
         *  ==================================================================================
        */

        self.popoverBuilder = stackutils.popoverBuilder;

        self.doStackAction = stackutils.doStackAction;

        self.showStackDetails = stackutils.showStackDetails;

        self.createNewStack = function (blueprint) {
            API.Users.load().then(function (public_key) {
                if (public_key === '') {
                    alerts.showMessage('#error', 'You have not saved your public key, and cannot launch any new stacks. Please open your user profile to save one.', true, 4000);
                } else {
                    $galaxy.transport({
                        location: 'stack.detail', 
                        payload: { 
                            blueprint: blueprint.id 
                        }
                    });
                }
            });
        };

        self.getStatusType = stackutils.getStatusType;

        self.refresh = function() {
            StackStore.populate(true);
        };

    };
    return new vm();
});
