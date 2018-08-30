from bluepy.btle import Peripheral

p = Peripheral("24:0a:c4:08:eb:4a")
print(p.getServices())
c = p.getCharacteristics(uuid="21428402-c7c4-4673-b87b-3a6facc302b8")[0]
s = p.getCharacteristics(uuid="6a023f58-3490-432f-893b-6292c522549f")[0]

print(c.read())
c.write(b'1')
s.write(b'1')
