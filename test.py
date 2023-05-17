


lst1 = [{"id": 1, "x": "one"}, {"id": 2, "x": "two 1"}]
lst2 = [{"id": 2, "x": "two 2"}, {"id": 3, "x": "three"}]

result = []
#lst1.extend(lst2)

result = {x['id']:x for x in lst1 + lst2}.values()


print(result)

exit()

for i in range(5):
    print(f"{i=}")

    for i2 in range(5):
        print(f"{i2=}")
        if i2==44:
            break
    
    else:
        print("Next loop")

exit()
