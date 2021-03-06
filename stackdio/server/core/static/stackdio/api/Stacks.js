/*!
  * Copyright 2014,  Digital Reasoning
  * 
  * Licensed under the Apache License, Version 2.0 (the "License");
  * you may not use this file except in compliance with the License.
  * You may obtain a copy of the License at
  * 
  *     http://www.apache.org/licenses/LICENSE-2.0
  * 
  * Unless required by applicable law or agreed to in writing, software
  * distributed under the License is distributed on an "AS IS" BASIS,
  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  * See the License for the specific language governing permissions and
  * limitations under the License.
  * 
*/

define(['q', 'settings', 'model/models'], function (Q, settings, models) {
    var api = {};

    api.load = function () {
        var deferred = Q.defer();

        $.ajax({
            url: settings.api.stacks.stacks,
            type: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            success: function (response) {
                var historyPromises = [],
                stacks = [];

                response.results.forEach(function (stack, index) {
                    historyPromises[historyPromises.length] = api.getHistory(stack).then(function (stackWithHistory) {
                        stacks[index] = new models.Stack().create(stackWithHistory);
                    });
                });

                Q.all(historyPromises).then(function () {
                    deferred.resolve(stacks);
                }).done();
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getStack = function (stackId) {
        var deferred = Q.defer();
        $.ajax({
            url: settings.api.stacks.stacks+stackId.toString()+'/',
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (stack) {
                deferred.resolve(stack);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getFQDNS = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: stack.fqdns,
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (response) {
                var history = response.results;
                stack.fullHistory = history;
                deferred.resolve(stack);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getLogs = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: stack.logs,
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (response) {
                deferred.resolve(response);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getLog = function (logUrl) {
        var deferred = Q.defer();

        $.ajax({
            url: logUrl,
            type: 'GET',
            headers: {
                'Accept': 'text/plain'
            },
            success: function (response) {
                deferred.resolve(response);
            },
            error: function (request, status, error) {
                deferred.reject(request.responseText);
                // deferred.reject(JSON.parse(request.responseText).detail);
            }
        });

        return deferred.promise;
    };

    api.getHistory = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: stack.history,
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (response) {
                var history = response.results;
                stack.fullHistory = history;
                stack.historyCount = response.count;
                deferred.resolve(stack);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.update = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: stack.url,
            type: 'PUT',
            data: JSON.stringify(stack),
            dataType: 'json',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': stackdio.settings.csrftoken,
                'Accept': 'application/json'
            },
            success: function (newStack) {
                api.getHistory(newStack).then(function (stackWithHistory) {
                    deferred.resolve(stackWithHistory);
                });
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };


    api.save = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: settings.api.stacks.stacks,
            type: 'POST',
            data: JSON.stringify(stack),
            dataType: 'json',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': stackdio.settings.csrftoken,
                'Accept': 'application/json'
            },
            success: function (newStack) {
                api.getHistory(newStack).then(function (stackWithHistory) {
                    deferred.resolve(stackWithHistory);
                });
            },
            error: function (request, status, error) {
                deferred.reject(JSON.parse(request.responseText).detail);
            }
        });

        return deferred.promise;
    };

    api.getHosts = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: stack.hosts,
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (response) {
                var hosts = response.results;                
                deferred.resolve(hosts);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getProperties = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: stack.properties,
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (properties) {
                deferred.resolve(properties);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getSecurityGroups = function (stack) {
        var deferred = Q.defer();

        $.ajax({
            url: stack.security_groups,
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (securitygroups) {
                deferred.resolve(securitygroups);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getActions = function (stack) {
        var deferred = Q.defer();
        
        $.ajax({
            url: stack.actions,
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (actions) {
                deferred.resolve(actions);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    api.getAction = function (actionId) {
        var deferred = Q.defer();
        
        $.ajax({
            url: '/api/actions/'+actionId.toString()+'/',
            type: 'GET',
            dataType: 'json',
            headers: {
                'Accept': 'application/json'
            },
            success: function (action) {
                deferred.resolve(action);
            },
            error: function (request, status, error) {
                deferred.reject(new Error(error));
            }
        });

        return deferred.promise;
    };

    return api;
});
