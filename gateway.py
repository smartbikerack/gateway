import threading
import requests
import json
import pymongo
from bluepy.btle import Peripheral, Scanner, DefaultDelegate
import os
from time import time, strftime, sleep
import datetime
import binascii


URL = "http://localhost:5000/"
PARKING_NUMBER =  1
SPOTS = ["24:0a:c4:08:eb:4a", "24:0a:c4:08:eb:4b"]
USER_UUID = "f2faeb57-d190-4657-ab17-b525e1d4ee53"
STATUS_UUID = "6a023f58-3490-432f-893b-6292c522549f"
ANNOUNCE_UUID = "21428402-c7c4-4673-b87b-3a6facc302b8"
OCCUPIED_UUID = "3ca17de4-73fe-4fd0-9e02-87433bb0385e"

myclient = pymongo.MongoClient("mongodb+srv://admin:masteriot@cluster0-yh0hh.gcp.mongodb.net/test?retryWrites=true")
mydb = myclient["smartbikerack"]

def verifyUser(userID):
    print(userID)
    query = {"uuid" : userID}
    user = mydb["users"].find_one(query, {"ObjectID" : 0, "password" : 0, "salt" : 0})
    if user == None:
        return {"user" : "False"}, False, False
    print(user)
    if user["status"] == "ok" and user["active"] == True:
        return user, True, user["current"]
    else:
        return {"user" :  "False"}, False, False

def updateUser(current, userID):
    query = {"uuid" : userID}
    change = {"$set" : {"current": current}}
    mydb["users"].update_one(query, change)
    return True

def updateParking(used, parking):
    query = {"number" : parking}
    parking = mydb["parking"].find_one(query)
    print(parking)
    spotsUsed = parking["spotsOccupied"]
    if used:
        spotsUsed+=1
    else:
        spotsUsed-=1
    if (0 <= spotsUsed) and (spotsUsed <= parking["spots"]):
        change = {"$set" : {"spotsOccupied" :  spotsUsed}}
        mydb["parking"].update_one(query, change)
        return True
    else:
        return False

def useSpot(user, spot):
    col = mydb["spot"]
    query = {"number": int(spot)}
    park = col.find_one(query)
    print("User {} trying to use spot {} on parking {}".format(user, spot, PARKING_NUMBER))
    print(park)
    userNumber, userStatus, userCurrent = verifyUser(user)
    if userStatus == False:
        print("User not valid")
        return False

    if userCurrent == True and park["occupiedBy"] != userNumber["number"]:
        print("User already using a spot")
        return False



    if park["occupied"] == False or park["occupiedBy"] == userNumber["number"]:
        now = datetime.datetime.now()
        dateName = now.strftime("%Y-%m-%d-%H-%M-%S")
        occupied = {"$set" : {"occupied" : True, "occupiedBy": userNumber["number"], "occupiedSince": dateName}}
        col.update_one(query,occupied)
        updateUser(True, user)
        if park["occupied"] == False:
            updateParking(True,PARKING_NUMBER)
        print("Parking used")
        return True
    return False

def releaseSpot(user, spot):
    query = {"number": int(spot), "parking": PARKING_NUMBER}
    col = mydb["spot"]
    spotInfo = col.find_one(query)
    print(spotInfo)
    print("User {} trying to release spot {} on parking {}".format(user, spot, PARKING_NUMBER))
    userNumber, userStatus, userCurrent = verifyUser(user)
    if userStatus == False:
        print("User not valid")
        return False

    if userCurrent == False:
        print("User not using any spot")
        return False

    if spotInfo["status"] == "down":
        return False

    if spotInfo["occupied"] == True and spotInfo["occupiedBy"] == userNumber["number"]:
        park = mydb["parking"].find_one({"number": PARKING_NUMBER})
        now = datetime.datetime.now()
        dateName = now.strftime("%Y-%m-%d-%H-%M-%S")
        free = {"$set" : {"occupied" : False, "occupiedBy": None, "occupiedSince": None}}
        mydb["spot"].update_one(query, free)
        then = datetime.datetime.strptime(spotInfo["occupiedSince"], "%Y-%m-%d-%H-%M-%S")
        timePassed = now - then
        print(str(timePassed.total_seconds()))
        cost = 0.001 * timePassed.total_seconds()
        mydb["uses"].insert_one({"user" : spotInfo["occupiedBy"], "start" : spotInfo["occupiedSince"],  "end" : dateName, "cost" : cost, "parking" : park["place"], "duration" : timePassed.total_seconds()})
        updateUser(False, user)
        updateParking(False, PARKING_NUMBER)
        print("Spot released")
        return True
    else:
        print("User trying to use an unauthorised spot")
    return False




class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            #print("Discovered device", dev.addr)
            pass
        elif isNewData:
            #print("Received new data from", dev.addr)
            pass

def newPetition(device):
    p = Peripheral(device)

    print(p.getServices())
    """
    c = p.getCharacteristics(uuid=STATUS_UUID)[0]
    user = p.getCharacteristics(uuid=USER_UUID)[0]
    status = p.getCharacteristics(uuid=STATUS_UUID)[0]
    """
    c = p.getCharacteristics(uuid=ANNOUNCE_UUID)[0]
    status = p.getCharacteristics(uuid=STATUS_UUID)[0]
    user_ble = p.getCharacteristics(uuid=USER_UUID)[0]
    user = user_ble.read()
    user_name =  str(user, 'ascii')[1:]
    print(user_name)
    occupied_ble = p.getCharacteristics(uuid=OCCUPIED_UUID)[0]
    occupied = int(occupied_ble.read())
    if occupied == 1:
        print("This spot is occupied")
        release_spot = releaseSpot(user_name, 1)
        if release_spot:
            status.write(b'1')
            c.write(b'1')
        else:
            status.write(b'3')
            c.write(b'1')
    elif occupied == 0:
        print("This spot is free")
        use_spot = useSpot(user_name, 1)
        if use_spot:
            status.write(b'1')
            c.write(b'1')
        else:
            status.write(b'3')
            c.write(b'1')
    else:
        pass


    p.disconnect()
    sleep(10)
    """
    print("Update values")
    status.write(b'1')
    c.write(b'1')
    print("Values written")
    p.disconnect()
    """


def main():
    scanner = Scanner().withDelegate(ScanDelegate())
    while True:
        devices = scanner.scan(1.0)
        for d in devices:
            for s in SPOTS:
                if s == d.addr:
                    #threading.Thread(target = newPetition, args=(s)).start()
                    #newPetition(s)
                    #os.system("python3 ble_connect.py")

                    try:
                        newPetition(s)
                    except Exception as e:
                        print(e)

if __name__ == "__main__":
    main()
