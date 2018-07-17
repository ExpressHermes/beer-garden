import _ from 'lodash';

adminUserController.$inject = [
  '$scope',
  'RoleService',
  'UserService',
  'PermissionService',
];

/**
 * adminUserController - System management controller.
 * @param  {$scope} $scope            Angular's $scope object.
 * @param  {Object} RoleService       Beer-Garden's role service object.
 * @param  {Object} UserService       Beer-Garden's user service object.
 * @param  {Object} PermissionService Beer-Garden's permission service object.
 */
export default function adminUserController(
    $scope,
    RoleService,
    UserService,
    PermissionService) {
  RoleService.getRoles()
  .then((response) => {
    $scope.roles = response.data;
  });

  UserService.getUsers()
  .then((response) => {
    $scope.users = response.data;
  });

  PermissionService.getPermissions()
  .then((response) => {
    $scope.permissions = _.groupBy(response.data, function(value) {
      return value.split('-').slice(0, 2).join('-');
    });
  });
};
