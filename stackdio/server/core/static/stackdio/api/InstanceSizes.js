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
    return {
        load : function () {
            var deferred = Q.defer();

            $.ajax({
                url: settings.api.cloud.instance_sizes,
                type: 'GET',
                headers: {
                    'Accept': 'application/json'
                },
                success: function (response) {
                    var sizes = response.results.map(function (size) {
                        return new models.InstanceSize().create(size);
                    });
                    deferred.resolve(sizes);
                },
                error: function (request, status, error) {
                    deferred.reject(new Error(error));
                }
            });

            return deferred.promise;
        }
    }
});