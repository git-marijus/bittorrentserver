# -*- coding: utf-8 -*-
'''
Created on 23.04.2017
@author: roere
'''
import sys
import os
import time
from threading import Thread
import configparser
import libtorrent as lt
from fileinput import filename

#torrentHandleList = [] #Storage for Torrent handles
torrentList = [] #Storage for Torrents
torrentName = {} #Torrent name by hash
magnetLinks = {} #magnetLink by hash
appName = "bittorrentserver"
basePath = "./addon/"+appName+"/"
cloudFileBasePath = "./"

#basePath = "./"
configFileName = appName+".cfg"
magnetURIFileName = "magnetURI.txt"

trackerList = []

class Logger:

    def __init__(self, filename):
        self.__filename = filename
        self.__logFile = open(os.path.normpath(basePath+filename),"w")
        
    def log (self, message):
        self.__logFile.write(message)
        self.__logFile.flush()    

#Controller: Get commands from PHP
def inputController(ses,):
    global run
    while run:
        logFile.write("Input Controller started...\n")
        logFile.flush()
        inputString = input()
            
        command = inputString[0:inputString.find("]")+1]
        param = inputString[inputString.find("]")+1:len(inputString)].split(",")
                
        logFile.write("IC: Input command recievded ...\n")
        logFile.flush()

        if command == "[ADD_TRACKER]":
            logFile.write("IC: Add Tracker ...\n")
            logFile.flush()
            
            appendTrackerList(param) # torrent nicht bekannt
            sys.stdout.flush()
        elif command == "[ADD_FILE]":
            logFile.write("IC: Add File ...\n")
            logFile.flush()
            
            #read parameters
            filename = str(param[1])
            filepath = str(param[0])
            
            fileStorage = lt.file_storage()
            lt.add_files(fileStorage, os.path.normpath(filepath+"/"+filename))
            lTorrent = lt.create_torrent(fileStorage) #lTorrent = localTorrent
            torrentList.append(lTorrent)
            addTrackerList(lTorrent)
            
            lTorrent.set_creator('Hubzilla using Libtorrent %s' % lt.version)
            lTorrent.set_comment("Filename:"+filename)
            lt.set_piece_hashes(lTorrent, os.path.normpath(filepath))
            gTorrent = lTorrent.generate() #gTorrent = generated Torrent
            
            ##write Torrent file to filesystem    
            tFile = open(os.path.normpath(filepath+"/"+filename+".torrent"), "wb")
            tFile.write(lt.bencode(gTorrent))
            tFile.close()
            
            handle = ses.add_torrent({'ti': lt.torrent_info(os.path.normpath(filepath+"/"+filename+".torrent")), 'name':filename, 'save_path': os.path.normpath(filepath), 'seed_mode': True})
            #torrentHandleList.append(handle)
            
            mLink = lt.make_magnet_uri(lt.torrent_info(gTorrent))
            logFile.write("IC: magnet uri:"+mLink+"\n")
            logFile.flush()
            
            print (mLink)
            sys.stdout.flush()

        else:
            pass
        time.sleep(1)
    logFile.write("SIGTERM: inputController ended...\n")
    logFile.flush()
            
#outputController: write status message into pingFile that can be read by the plugin
def outputController (ses,):
    global run
    try:
        logFile.write("OutputController started...\n")
        logFile.flush()
        while run:
            with open(os.path.normpath(basePath+appName+".ping"),"w") as pingFile:
                pingFile.write('['+time.strftime("%d.%m.%Y - %H:%M:%S")+'] Process ID: '+str(os.getpid())+' Listening on: %d' % \
                               (ses.listen_port()))
                torrentHandleList = ses.get_torrents()
                for handle in torrentHandleList:
                    s = handle.status()
                    state_str = ['queued', 'checking', 'downloading metadata', \
                                 'downloading', 'finished', 'seeding', 'allocating', 'checking fastresume']
                    pingFile.write(('\n%.2f%% complete (down: %.1f kb/s up: %.1f kB/s peers: %d) %s ('+torrentName[str(handle.get_torrent_info().info_hash())]+')') % \
                                    (s.progress * 100, s.download_rate / 1000, s.upload_rate / 1000, s.num_peers, state_str[s.state]))
            pingFile.close()
            time.sleep(10)   
        logFile.write("SIGTERM: outputController ended...\n")
        logFile.flush()
    except:
        logFile.write("Unexpected error in outputController:\n->"+str(sys.exc_info()[0])+"\n->"+str(sys.exc_info()[1])+"\n->"+str(sys.exc_info()[2])+"\n")
        logFile.flush()
        run = False
    
#configFileController: check config File for changes and react on them    
def configFileController (ses,):
    global run, appName, basePath
    stamp = "" #time stamp of cfg-file
    try:
        logFile.write("ConfigFileController started...\n")
        logFile.flush()
        while run: 
            if (stamp != os.stat(basePath+configFileName).st_mtime):
                stamp = os.stat(basePath+configFileName).st_mtime
                
                config = configparser.ConfigParser()
                fp = open(os.path.normpath(basePath+configFileName))
                config.readfp(fp)
                
                #config.read(os.path.normpath(basePath+configFileName))
                if config["Controller"]["sigterm"] == "1":
                    run = False  
                    fp.close()
                    logFile.write("SIGTERM recieved...\n")
                    logFile.flush()
                elif config["Controller"]["sigreload"] == "1":
                    logFile.write("SIGRELOAD: reloading config file...\n")
                    logFile.flush()
                    #add Trackers
                    trackerList = config.items("Tracker")
                    lList = []
                    for tracker in trackerList:
                        lList.append(tracker[1].replace("\"",""))
                    appendTrackerList(lList)
                    
                    #add Files
                    with open(os.path.normpath(basePath+magnetURIFileName), 'w') as magnetURIOutFile:
                        
                        #Before adding new torrent files to the the session, we remove all currently active torrents from the session
                        #and delete all files in the torrents directory.
                        #Should be checked if there is a more efficient way.
                        aTorrentList = ses.get_torrents()
                        for torrent in aTorrentList:
                            ses.remove_torrent(torrent)
                        fList = os.listdir(os.path.normpath(basePath+"torrents"))
                        for df in fList:
                            os.remove(os.path.normpath(basePath+"torrents/"+df))
                        
                        fileList = config.items("File")
                        
                        #check all files
                        j=0
                        for mFile in fileList:
                            j=j+1
                            fRaw = mFile[1].replace("\"","") #delete " in file name
                            i = fRaw.rfind("/")
                            if i==-1: #just file name given? we expect the file relative to basePath 
                                fPath = basePath
                                fName = fRaw
                            else:
                                fName = fRaw[i+1:] #extract file name from given path
                                if fRaw[0]=="/": #absolute path defined?
                                    fPath = fRaw[:i+1]
                                else:
                                    fPath = basePath+fRaw[:i+1] #relative path? add basePath!
        
                            logFile.write("SIGRELOAD: reloading:"+fPath+"---"+fName+"\n")
                            logFile.flush()
                            if os.path.isfile(fPath+fName):
                                mLink = addTorrent(fPath, (basePath+"torrents/"), fName, fName)
                                logFile.write("SIGRELOAD: Magnet-Link:"+mLink+"\n")
                                logFile.flush()
                                magnetURIOutFile.write("["+str(j)+"] "+mLink+"\n")
                            else:
                                logFile.write("SIGRELOAD: file not found:"+os.path.normpath(fPath+fName)+"\n")
                                logFile.flush() 
                                magnetURIOutFile.write("["+str(j)+"] File not found:"+os.path.normpath(fPath+fName)+"\n")       
                        
                        #Cloud Files start
                        if config.has_section ("Cloudfile"):
                            cloudFileList = config.items("Cloudfile")
                            logFile.write("SIGRELOAD: has section Cloudfile\n")
                            logFile.flush()
                            #check all files
                            for cFile in cloudFileList:
                                j=j+1
                                fRaw = cFile[0]
                                i = fRaw.rfind("/")
                                osfName = fRaw[i+1:] #extract hashed file name   
                                fPath = cloudFileBasePath+fRaw[:i+1]
                                fName = cFile[1].replace("\"","")
                                #fName = fName.encode('utf8','strict').decode('unicode_escape') #real file name. Decoding: The Python ConfigParser is not able to read mutated vowels, etc.
                                
                                logFile.write("SIGRELOAD: CF extracted: encoded\n")
                                logFile.flush()
                                
                                logFile.write("SIGRELOAD: reloading:"+fPath+"--- ("+fName+")\n")
                                logFile.flush()
                                if os.path.isfile(fPath+osfName):
                                    mLink = addTorrent(fPath, (basePath+"torrents/"), osfName, fName)
                                    logFile.write("SIGRELOAD: Magnet-Link:"+mLink+"\n")
                                    logFile.flush()
                                    magnetURIOutFile.write("["+str(j)+"] "+mLink+"\n")
                                else:
                                    logFile.write("SIGRELOAD: file not found:"+os.path.normpath(fPath+osfName)+" ("+fName+")\n")
                                    logFile.flush() 
                                    magnetURIOutFile.write("["+str(j)+"] File not found:"+os.path.normpath(fPath+osfName)+" ("+fName+"\n")    
                        else:
                            logFile.write("SIGRELOAD: has NO section Cloudfile")
                            logFile.flush()
                            #Cloud Files end
                           
                    magnetURIOutFile.close()
                    config["Controller"]["sigreload"] = "0"
                    fp.close()
                    with open(os.path.normpath(basePath+configFileName), 'w') as fp:
                        config.write(fp)
                    fp.close()
                    logFile.write("SIGRELOAD: reset!...\n")
                    logFile.flush()  
            else:
                time.sleep(1)
        logFile.write("SIGTERM: configFileController ended...\n")
        logFile.flush()
    except:
        logFile.write("Unexpected error in ConfigFileController:\n-> "+str(sys.exc_info()[0])+"\n-> "+str(sys.exc_info()[1])+"\n-> "+str(sys.exc_info()[2])+"\n")
        logFile.flush()
        run = False
    
#Add Bittorrent-Tracker
def addTracker (tracker):
    global trackerList, torrentList
    if not (tracker in trackerList):
        trackerList.append(tracker)
    for torrent in torrentList:
        torrent.add_tracker(tracker)
    #torrentHandleList = ses.get_torrents()
    #for handle in torrentHandleList:
    #    handle.add_tracker(tracker)

#Remove Bittorrent-Tracker
def removeTracker (tracker):
    global trackerList
    if (tracker in trackerList):
        trackerList.remove(tracker)
    #ToDo: remove tracker from torrent.
    
#Append Tracker-List to global Tracker List
def appendTrackerList (localTrackerList):
    for tracker in localTrackerList:
        addTracker(tracker)

#Add Trackerlist to Torrent
def addTrackerList (torrent):
    for tracker in trackerList:
        torrent.add_tracker(tracker)
            
#
def addTorrent (filepath, torrentpath, osfilename, filename):
    global torrentName, ses, torrentList #, torrentHandleList
    fileStorage = lt.file_storage()
    lt.add_files(fileStorage, os.path.normpath(filepath+osfilename))
    lTorrent = lt.create_torrent(fileStorage) #lTorrent = localTorrent
    torrentList.append(lTorrent)
    addTrackerList(lTorrent)
    
    lTorrent.set_creator('Hubzilla using Libtorrent %s' % lt.version)
    lTorrent.set_comment("Filename:"+filename.encode('utf8','strict').decode('unicode_escape'))
    
    lt.set_piece_hashes(lTorrent, os.path.normpath(filepath))
    gTorrent = lTorrent.generate() #gTorrent = generated Torrent
    
    ##write Torrent file to filesystem    
    tFile = open(os.path.normpath(torrentpath+filename+".torrent"), "wb")
    tFile.write(lt.bencode(gTorrent))
    tFile.close()
    
    handle = ses.add_torrent({'ti': lt.torrent_info(os.path.normpath(torrentpath+filename+".torrent")), 'save_path': os.path.normpath(filepath), 'seed_mode': True})
    #torrentHandleList.append(handle)
    torrentName[str(handle.get_torrent_info().info_hash())] = filename
    
    mLink = lt.make_magnet_uri(lt.torrent_info(gTorrent))
    magnetLinks[str(handle.get_torrent_info().info_hash())] = mLink
    return mLink
            
#Seed torrent
ses = lt.session()
ses.listen_on(6881, 6891)

#T3
#ses.add_extension('ut_metadata')
#ses.add_extension('ut_pex')

#ses.add_dht_router("router.utorrent.com", 6881)
#ses.add_dht_router("router.bittorrent.com", 6881)
#ses.add_dht_router("dht.transmissionbt.com", 6881)
#ses.add_dht_router("router.bitcomet.com", 6881)
#ses.add_dht_router("dht.aelitis.com", 6881)
#ses.start_dht()

#ses.start_dht()
#ses.start_lsd()
#ses.start_upnp()
#ses.start_natpmp()
#T3   
     
#open logfile
logFile = open(os.path.normpath(basePath+"bittorrentserver.log"),"w")
logger = Logger("bittorrentserver.log")

#programm stops, when run is false
run = True
     
#start new thread for PHP input
t1 = Thread(target=inputController, args=(ses,))
t1.daemon = True
t1.start()

#start new thread for PHP outpu
t2 = Thread(target=outputController, args=(ses,))
t2.daemon = True
t2.start()

#start new thread for config file controll
t3 = Thread(target=configFileController, args=(ses,))
t3.daemon = True
t3.start()

while run:
    time.sleep(1)
   
logFile.write("SIGTERM: waiting for all processes to terminate...\n")
logFile.flush()
time.sleep(5)

logFile.write("SIGTERM: Main thread ended...\n")
logFile.flush()
