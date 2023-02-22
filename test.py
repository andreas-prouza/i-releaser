
from modules import ibm_i_commands as ic, deploy_action

print(deploy_action.Processing_Area.is_valid('prex'))
print(deploy_action.Processing_Area.get_values())
exit()

a = ic.Deploy_Action_List()

a.add_action_cmd("dsp1")
a.add_action_cmd("dsp2")

print(a.get_list())
exit()


a='2023-02-10 08:50:39.265417'

a=[{'key1': 'value23'}, {'key1': 'value2'}]
b=[{'key2': 'value2'}, {'key1': 'value1'}]

def get_value(x):
  return x.get('key1')

#print(a[0].get('key1'))
a.sort(key=get_value)
#print(a)

#exit()

#print(str(a == b))

a = [{'Manjeet' : 12, 'Himani' : 15}, {'Akshat' : 20, 'Vashu' : 15}]
b = [{'Himani' : 15, 'Manjeet' : 12}, {'Vashu' : 15, 'Akshat' : 20}]

#print('Are Dictionary Lists equal ? : ' + str(a == b))


a = [
            {
                "lib": "prouza2",
                "savf": "prouza2savf"
            },
            {
                "lib": "prouzalib",
                "savf": "prouzalibsavf"
            }
        ]

print([x['savf'] for x in a if x['deploy_lib']=='prouza2'])