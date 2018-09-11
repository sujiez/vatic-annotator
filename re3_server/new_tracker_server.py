import argparse
import cPickle
import socket
import struct
import threading
import time
import cv2
import glob

import sys
import os.path
import threading
import datetime
import logging
from pylru import lrucache

# sys.path.append("/home/sujiez/re3-duplicate/tools")
#sys.path.append("/home/sujiez/re3-tensorflow/tracker")
sys.path.append("/home/robolab/re3-tensorflow-private/tracker")
from re3_multi_tracker import Re3TrackerFactory

HOST = 'localhost'
PORT = 9997
POOL_SIZE = 1

logging.basicConfig(level=logging.DEBUG)


class Re3_server:
    """
    About a server that can process tracking request.
    Let the user hold a server and terminate it.
    The max number of request that this server can handle at the same time is 10, default to 8.

    :param host: host address
    :param port: port to hold the server
    :param pool_size: how many request to handle at the same time
    :param image_path: a list of directory path which contains image of chunk video, default to None
    """

    def __init__(self, host, port, pool_size, image_path=None):
        self.check_version = "Re3_1024"  # for check if the request is valid

        self.address = (host, port)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(self.address)

        self.tracker_factory = Re3TrackerFactory() # a module to create trackers

        # to lock 1.tracker_pool  2.number_pool
        self.pool_lock = threading.Lock()
        # to notify if the server have room to accept next request
        self.next_request_CV = threading.Condition(self.pool_lock)

        if pool_size > 10 or pool_size <= 0:
            pool_size = 8
            pass
        self.pool_size = pool_size
        # a dict that map from number to be assigned to requests and trackers
        self.tracker_pool = {}
        # current free number for requests
        self.number_pool = []
        self.create_pool()

        # the thread that run the server at backend if user specify
        self.re3_server = None

        # how many np image to buffer
        self.cache_size = 2048
        self.buffer_lock = threading.Lock()
        # lru to buffer parsed image
        self.image_buffer = lrucache(self.cache_size)
        self.parse_image_buffer(image_path)

        # for debug
        self.first_bb = None # the last no-fake bb of recent
        self.first_bb_time = 0 # how many time the no-fake bb received
        # self.fd_lock = threading.Lock()
        pass

    def parse_image_buffer(self, image_path):
        """
        Parse image using the directory specified by image_path

        :param image_path: a list of directories that contains image
        :return:
        """
        if image_path:
            result_path = [] # image paths
            for path in image_path: # directory path
                outer_path = glob.glob(path + "/[0-9]")
                for outer in outer_path: # scale to every 100 frames
                    inner_path = glob.glob(outer + "/[0-9]")
                    for inner in inner_path: # scale to every frames
                        images = glob.glob(inner + "/*.jpg")
                        result_path += images
                        pass
                    pass
                pass
            result_path = result_path[:self.cache_size]
            for path in result_path:
                self.image_buffer[path] = cv2.imread(path)[:, :, [2, 1, 0]]
                pass
            pass
        pass


    def create_pool(self):
        """
        Create a pool of trackers

        :return:
        """
        for x in range(self.pool_size):
            self.number_pool.append(x)
            new_tracker = self.tracker_factory.create_tracker()
            self.tracker_pool[x] = new_tracker
            pass
        pass


    def start_serve(self, daemon=False):
        """
        Start the server

        :param daemon: a boolean value to specify whether run the server in the background
        :return:
        """
        time_header = self.giveTime()
        logging.info(time_header + ">>> Re3 tracker listen on " +
                     self.address[0] + " : " + str(self.address[1]))
        logging.info("length of number pool" + str(len(self.number_pool)))
        logging.info("length of the tracker pool" + str(len(self.tracker_pool)))

        if not daemon:
            self.serve_helper()
        else:
            self.re3_server = threading.Thread(target=self.serve_helper)
            self.re3_server.start()
            pass
        pass


    def stop_serve(self):
        """

        :return:
        """
        try:
            self.server_socket.shutdown(socket.SHUT_RDWR) # close the server socket
            # self.server_socket.close()
            self.re3_server.join()
        except:
            logging.info("*****catch exception in line 149 " + str(sys.exc_info()[0]))
            pass
        pass


    def serve_helper(self):
        """
        Function to serve requests

        :return:
        """
        try:
            self.server_socket.listen(5)
            while True:
                (request_socket, request_address) = self.server_socket.accept()

                self.next_request_CV.acquire()
                if len(self.number_pool) == 0:  # if there is no available space
                    # logging.info("\n\n\n\n\n *************hahahahahhaa you got this")
                    self.next_request_CV.wait()
                    pass

                request_pointer = self.number_pool.pop(0)  # get the number to assign to requests

                request_handler = threading.Thread(target=self.handle_request,
                                                   args=[request_pointer, request_socket, self.tracker_pool[request_pointer]])
                self.next_request_CV.release()
                # request_socket.settimeout(8) # need this ??????????
                request_handler.start()
                pass
        except socket.error as e:
            logging.info("******catch socket error in line 184 " + str(e))
            pass
        finally:
            self.server_socket.close()
            if self.pool_lock.locked():
                self.next_request_CV.release()
                pass
            pass
        pass


    def handle_request(self, request_pointer, request_socket, request_tracker):
        """
        Function to handle the tracking request

        :param request_pointer: serial number of current request
        :param request_socket:  socket to receive and send
        :param request_tracker: tracker for current request
        :return:
        """
        fd = None
        try:
            # self.fd_lock.acquire()
            # fd = open("/home/sujiez/test/server_log.txt", 'a')
            # self.fd_lock.release()

            hand_wave = request_socket.recv(128).strip()
            if hand_wave != self.check_version: # check valid request
                """
                TODO:
                    remember to remove
                """
                # os._exit(1)
                raise Exception("version check failed")

            request_socket.send("Ready")

            expect_length = struct.unpack('>I', request_socket.recv(4))[0]

            request_information = ""
            while len(request_information) < expect_length:
                addOn = request_socket.recv(min(1024, expect_length - len(request_information)))
                request_information += addOn
                pass

            if len(request_information) == 0:
                """
                TODO:
                    remember to remove
                """
                # os._exit(1)
                raise Exception("invalid request!")

            logging.info("request information got!\n")

            # self.fd_lock.acquire()
            # fd.write("request information got!\n\n")
            # fd.flush()
            # self.fd_lock.release()

            first_bb, image_paths, object_id = cPickle.loads(request_information)
            result = []

            if first_bb != [-1, -1, -1, -1]:
                logging.info("get object_id " + str(object_id))
                logging.info("get image_paths " + str(image_paths))
                logging.info("get first bb " + str(first_bb))

                # self.fd_lock.acquire()
                # fd.write("get object_id " + str(object_id) + "\n")
                # fd.write("get image_paths " + str(image_paths) + "\n")
                # logging.info("get first bb " + str(first_bb) + "\n")
                # self.fd_lock.release()

                request_tracker.track(object_id, image_paths[0], first_bb)

                image_paths = image_paths[1:]
                result.append(tuple(first_bb))
                # for check
                self.first_bb = first_bb
                self.first_bb_time += 1
                pass


            # self.fd_lock.acquire()
            # fd.write("id: " + object_id + "\n")
            # self.fd_lock.release()

            for image_path in image_paths:
                logging.info("image path = " + image_path)

                # self.fd_lock.acquire()
                # fd.write("image path = " + image_path + "\n")
                # self.fd_lock.release()

                self.buffer_lock.acquire()
                if image_path not in self.image_buffer:
                    parsed_image = cv2.imread(image_path)[:, :, [2, 1, 0]]
                    self.image_buffer[image_path] = parsed_image
                else:
                    parsed_image = self.image_buffer[image_path]
                    pass
                self.buffer_lock.release()

                next_bb = request_tracker.track(object_id, parsed_image)

                result.append(tuple(next_bb))
                pass


            logging.info("length of result is: " + str(len(result)))
            logging.info("Done with tracking \n")
            logging.info("Very first bb " + str(self.first_bb))
            logging.info("Current first bb " + str(first_bb))
            logging.info("given bb time " + str(self.first_bb_time))
            logging.info("object id " + str(object_id))

            # self.fd_lock.acquire()
            # fd.write("length of result is: " + str(len(result)))
            # fd.write("Done with tracking \n")
            # fd.write("Very first bb " + str(self.first_bb))
            # fd.write("Current first bb " + str(first_bb))
            # fd.write("given bb time " + str(self.first_bb_time))
            # fd.write("object id " + str(object_id))
            # self.fd_lock.release()

            result_bb = cPickle.dumps(result)

            logging.info("\ngot result bb ")
            logging.info(str(cPickle.loads(result_bb)) + "\n")

            # self.fd_lock.acquire()
            # fd.write("\ngot result bb ")
            # fd.write(str(cPickle.loads(result_bb)) + "\n")
            # self.fd_lock.release()

            result_bb_length = struct.pack('>I', len(result_bb))
            request_socket.sendall(result_bb_length)
            request_socket.sendall(result_bb)
        except socket.error as e:
            logging.info("*****Caught exception in line 272 " + str(e))
            os._exit(1)
            raise e
            # logging.info("*****Caught exception in line 272 " + str(sys.exc_info()[0]))
        finally:
            if self.buffer_lock.locked():
                self.buffer_lock.release()

            # if not self.fd_lock.locked():
            #     self.fd_lock.acquire()
            #
            # fd.close()
            # self.fd_lock.release()

            request_socket.close()
            self.next_request_CV.acquire()
            self.number_pool.append(request_pointer)
            self.next_request_CV.notify()
            self.next_request_CV.release()
            pass
        pass


    def giveTime(self):
        current_time = datetime.datetime.now()
        result = str(current_time.day) + " " + str(current_time.month) + " " + \
                 str(current_time.hour) + ":" + str(current_time.minute) + ":" + \
                 str(current_time.second) + " - "
        return result


def main(args):
    """
    The main function which make a Re3_server class and tracking requests

    :param args: contains program arguments
    :return:
    """
    port = args.port
    pool_size = args.pool_size
    # the max client number is 10
    if pool_size > 10 or pool_size <= 0:
        pool_size = POOL_SIZE
        pass
    re3_server = Re3_server(HOST, port, pool_size, args.image_path)
    re3_server.start_serve(True)
    # listen for stdin to terminate the server
    while True:
        try:
            command = raw_input()
            # if not command or command == "q":
            if command == "q":
                break
        except EOFError:
            break
        pass
    re3_server.stop_serve()
    pass


if __name__ == '__main__':
    '''
    Parse arguments and run the main function
    '''
    parser = argparse.ArgumentParser(
            description='Re3 Tracker Server (image paths, size of tracker pool and port number)')

    parser.add_argument('-p', '--port', action='store', default=PORT,
                        dest='port', type=int)

    # specify how many client can run at the same time
    parser.add_argument('-s', '--size', action='store', default=POOL_SIZE,
                        dest='pool_size', type=int)

    # specify path to directories of images, given as list
    parser.add_argument('-i', '--imagePath', dest="image_path", nargs='+')
    args = parser.parse_args()

    main(args)
    pass
