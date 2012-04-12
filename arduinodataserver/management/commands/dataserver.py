import sys, os, threading, time
from datetime import datetime
from django.core.management.base import BaseCommand
from optparse import make_option

import SocketServer

from arduinodataserver import models

class MyTCPHandler(SocketServer.BaseRequestHandler):
    """
    The RequestHandler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
        print "Got connection"

        data_received = ""
        last_count_inserted = {}
        base_offset = {}
        
        while True:
            time.sleep(0.1)
            self.data = self.request.recv(1024).strip()
            print "Received connection from %s" % str(self.client_address[0])
            
            data_received += self.data
            values_received = data_received.split(";")
            if len(data_received) > 30:
                return
            if not values_received or not "" == values_received[-1]:
                continue
            values_received = filter(lambda x: x!="", values_received)
            
            for value in values_received:
                try:
                    meter_id, meter_count = value.split(":")
                    meter_count = int(meter_count)
                    
                    meter = models.Meter.objects.get(id=int(meter_id))
                    if not last_count_inserted.get(meter_id, None):
                        latest_data = models.MeterData.objects.filter(meter=meter).order_by('-id')
                        diff = 1
                        insert_count = 0
                        latest_data_count = 0
                        if latest_data:
                            base_offset[meter_id] = latest_data[0].data_point
                            latest_data_count = 0 #latest_data[0].data_point
                        else:
                            base_offset[meter_id] = 0

                        insert_count = meter_count + base_offset[meter_id]
                        diff = meter_count - latest_data_count
                        
                    else:
                        
                        if meter_count > latest_data_count:
                            latest_data_count = last_count_inserted[meter_id]
                            insert_count = meter_count - latest_data_count + base_offset[meter_id]
                            diff = insert_count - latest_data_count
                        
                        else:
                            # Meter must have reset itself!
                            latest_data_count = last_count_inserted[meter_id]
                            insert_count = meter_count + base_offset[meter_id]
                            diff = insert_count - latest_data_count
                        
                    data = models.MeterData(data_point=insert_count,
                                            meter=meter,
                                            created = datetime.now(),
                                            diff=diff)

                    last_count_inserted[meter_id] = meter_count
                    base_offset[meter_id] = insert_count
                    print "Inserting value %d - received value %d" % (insert_count, meter_count)
                    data.save()
                    
                except ValueError:
                    print "Not an integer", value
                    return
                except IndexError:
                    print "No meter value received -- must be ID:VALUE"
                    continue
                except models.Meter.DoesNotExist:
                    print "No meter with this ID", meter_id
                    continue
            
            data_received = ""
            

    def finish(self):
        print "Connection closed"
        return SocketServer.BaseRequestHandler.finish(self)
    
class Command(BaseCommand):
    args = ('--dummy')
    help = 'Runs a server that listens to the arduino' #@ReservedAssignment
    option_list = BaseCommand.option_list + (
        make_option('--daemon', '-d', dest='daemon', default=False,
                    action='store_true',
                    help='Rum in daemon mode'),
        make_option('--pid-file', action='store', dest='pid',
                    default="/tmp/powermeterdaemon.pid", 
                    help='Specify a file to put our process ID in (for daemon mode)'),
        make_option('--addr', action='store', dest='addr',
                    default="localhost", 
                    help='Specify the ip address to listen to.'),
        make_option('--port', '-p', action='store', dest='port',
                    default="9999", 
                    help='Specify a TCP port for listening.'),
        )
    def handle(self, *args, **options):
        
        daemon = options['daemon']
        pid_file_name = options['pid']
        addr = options['addr']
        port = int(options['port'])
        
        HOST, PORT = addr, port
    
        # Create the server, binding to localhost on port 9999
        SocketServer.TCPServer.allow_reuse_address = True
        server = SocketServer.TCPServer((HOST, PORT), MyTCPHandler)

        server_thread = threading.Thread(target=server.serve_forever, args=())
        server_thread.setDaemon(True)
        server_thread.start()

        # Run as daemon, ie. fork the process
        if daemon:
            fpid = os.fork()
            if fpid!=0:
                # Running as daemon now. PID is fpid
                pid_file = file(pid_file_name, "w")
                pid_file.write(str(fpid))
                pid_file.close()
                sys.exit(0)

        while True:
            try:
                print "Running server"
                time.sleep(20)
            except:
                print "Quitting server"
                server.server_close()
                sys.exit(1)
