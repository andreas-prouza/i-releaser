from modules.permission import Permission


C_ALLOWED_USERS = [
  'PROUZA',
  'PROUZAT1'
]


USER_PERMISSION =  {
    'PROUZA': {
      'general': [Permission.READ],
      'workflows': {
        'academy_test_build': {
          'general': [Permission.READ],
          'stages': {
              'uat': [Permission.ADMIN]
            }
        }
      }
    },
    'PROUZAT1': {
      'workflows': {
        'academy_test_build': {
          'general': [Permission.READ],
          'stages': {
              'uat': [Permission.FOUR_EYES_CHECK]
            }
        }
      }
    }
  }
