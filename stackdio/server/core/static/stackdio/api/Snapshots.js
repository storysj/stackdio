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

define(['q', 'model/models', 'settings'], function (Q, models, settings) {
    return {
        load : function () {
            var deferred = Q.defer();

            $.ajax({
                url: settings.api.stacks.snapshots,
                type: 'GET',
                headers: {
                    "Accept": "application/json"
                },
                success: function (response) {
                    var snapshots = response.results.map(function (s) {
                        var snapshot = new models.Snapshot().create(s);
                        return snapshot;
                    });

                    deferred.resolve(snapshots);
                },
                error: function (request, status, error) {
                    deferred.reject(new Error(error));
                }
            });

            return deferred.promise;
        },
        save: function (snapshot) {
            var deferred = Q.defer();

            console.log(snapshot);

            $.ajax({
                url: settings.api.stacks.snapshots,
                type: 'POST',
                data: JSON.stringify(snapshot),
                headers: {
                    'X-CSRFToken': stackdio.settings.csrftoken,
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                success: function (response) {
                    deferred.resolve(new models.Snapshot().create(response));
                },
                error: function (request, status, error) {
                    deferred.reject(JSON.parse(request.responseText).errors);
                }
            });

            return deferred.promise;
        },
        delete: function (snapshot) {
            var deferred = Q.defer();

            $.ajax({
                url: snapshot.url,
                type: 'DELETE',
                headers: {
                    "X-CSRFToken": stackdio.settings.csrftoken,
                    "Accept": "application/json"
                },
                success: function (response) {
                    deferred.resolve();
                },
                error: function (request, status, error) {
                    deferred.reject(new Error(error));
                }
            });

            return deferred.promise;
        },
        options: function () {
            var deferred = Q.defer();

            $.ajax({
                url:  settings.api.stacks.snapshots,
                type: 'OPTIONS',
                headers: {
                    "X-CSRFToken": stackdio.settings.csrftoken,
                    "Accept": "application/json"
                },
                success: function (data, textStatus, qwerty) {
                    deferred.resolve({verbs: qwerty.getResponseHeader('Allow').split(',') });
                },
                error: function (request, status, error) {
                    deferred.reject(new Error(error));
                }
            });
            
            return deferred.promise;
        }
    }
});