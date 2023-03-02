
from modules import ibm_i_commands as ic, deploy_action, deploy_action as da, stages as s, meta_file

from pathlib import Path
import os

path = Path("/here/your/path/file.txt")
print(os.path.basename(os.path.dirname("/here/your/path/file.txt")))
exit()

aa={"b": 'xxx', "c": "cccc", "x": ['START', 'END']}
print(*aa.get('x'))
a='test {b} {c} test2 x1: {x[0]}, x2: {x[1]}, {x}'.format(**aa)
print(a)
exit()

a={'key1': 'value23', 'key2': None}
if 'key2' in a.keys():
    print('Ja, alles da')
print(a.keys())
exit()


m = meta_file.Meta_File()
m.import_objects_from_config_file2('prod_obj.txt')
print(m.get_all_data_as_dict())
exit()

#print(s.Stage.get_stage('PROD'))
stages=s.Stage_List_list(['END', s.Stage.get_stage('PROD')])
#stages.append(s.Stage.get_stage('PROD'))
print(stages)
exit()

a=['b', 'a', 'd', 'e']
b=['a', 'b', 'c', 'x'] # Basis
print(set(a) - set(b))
exit()

print(deploy_action.Processing_Step.is_valid('prex'))
print(deploy_action.Processing_Step.get_values())
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