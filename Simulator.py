# imports 
import time

from io import BytesIO

from Classes import *
from Network import *
from Drone import *
#from PIL import Image

class Simulator:
    def __init__(self):
        pass

    def start(self):
        # init drones
        self.drones = [Drone(i) for i in range(Constants.num_drones)]

        Constants.renderer = MapRenderer(Constants.grid_dimension.x, Constants.grid_dimension.y)
        Constants.network = NetworkLayer(self.drones, self)

        # First get blocks of image points and drones
        self.blocks = Utility.getGridBlocks()

        # Equally Distribute blocks in drones
        self.allocations_list = Utility.get_grid_distribution(self.blocks)

        # Reshuffle without considering relay time already alternated
        self.allocations_list = Utility.shuffle_distribution(self.allocations_list, self.drones)

        self.connected_drones = []
        self.all_connected = False
        self.all_connected_time = None

        self.relay_points = []
        self.near_blocks = []
        self.empty_allocations = []

        #Constants.renderer.close()

    def generate_relay(self, time):
        self.empty_allocations = []
        # Update allocation times
        for i, allocations in enumerate(self.allocations_list):
            not_completed = [block for block in allocations if not block.completed]
            if len(not_completed) != 0:
                Utility.set_estimated_time(not_completed, self.drones[i])
            else:
                self.empty_allocations.append(i)

        # if all completed then go back
        if len(self.empty_allocations) == Constants.num_drones:
            self.empty_allocations = []
            raise ValueError("All Completed")


        # get nearest grid location for next time
        blocks = []
        drange = Constants.drone_range * 0.9
        for i, allocations in enumerate(self.allocations_list):
            if i in self.empty_allocations:
                blocks.append(None)
            else:
                blocks.append(sorted(allocations, key=lambda x: abs(x.estimated_time - time))[0])

        def _get_intersection(pt1, center, radius):
            # get slope of line
            y1 = math.sqrt(radius ** 2 - (pt1.x - center.x) ** 2) + center.y
            y2 = -math.sqrt(radius ** 2 - (pt1.x - center.x) ** 2) + center.y
            return Vector2D(pt1.x, y1) if y1 > y2 else Vector2D(pt1.x, y2)

        # get relay points
        relay_points = [Constants.server_loc, ]
        
        # scaling of the relay points TODO
        for i, block in enumerate(blocks):
            # skip if empty allocations
            if i in self.empty_allocations:
                relay_points.append(self.relay_points[i])
                continue

            # check if inside range
            vec = block.loc.sub(relay_points[i])
            mag = vec.abs()
            if mag < drange:
                # push it in y
                relay_points.append(_get_intersection(block.loc, relay_points[i], drange))
            else:
                vec = vec.mul(1 / mag)
                relay_points.append(vec.mul(drange).add(relay_points[i]))

        # scaling of the relay points
        last_x = max(relay_points, key=lambda x: x.x).x
        last_y = max(relay_points, key=lambda x: x.y).y

        scale_x = 1
        scale_y = 1

        if last_x < 0 or last_x > Constants.grid_dimension.x:
            if last_x < Constants.server_loc.x:
                scale_x = abs(0 - Constants.server_loc.x) / abs(last_x - Constants.server_loc.x)
            else:
                scale_x = abs(Constants.grid_dimension.x - Constants.block_width / 2 - Constants.server_loc.x) / abs(
                    last_x - Constants.server_loc.x)

        if last_y < 0 or last_y > Constants.grid_dimension.y:
            if last_y < Constants.server_loc.y:
                scale_y = abs(0 - Constants.server_loc.y) / abs(last_y - Constants.server_loc.y)
            else:
                scale_y = abs(Constants.grid_dimension.y - Constants.block_height / 2 - Constants.server_loc.y) / abs(
                    last_y - Constants.server_loc.y)

        for j, relay_pt in enumerate(relay_points):
            if j in self.empty_allocations:
                continue
            x = relay_pt.x * scale_x
            y = relay_pt.y * scale_y
            relay_points[j] = Vector2D(x, y)
        return blocks, relay_points[1:]

    def process_relay(self, near_blocks, relay_points, relay_time):
        try:
            relay_points = [GridBlock((-2, -2), relay_points[i], (0 ,0 ,0)) for i in range(len(relay_points))]
            for i, block in enumerate(near_blocks):
                if i in self.empty_allocations:
                    self.drones[i].state = DroneState.COMPLETED_WAITING
                    continue
                index = self.allocations_list[i].index(block)
                index_first_not_completed = [ind for ind, grpt in enumerate(self.allocations_list[i])
                                             if grpt.completed == False][0]
                if block.estimated_time > relay_time:
                    sublist = self.allocations_list[i][index_first_not_completed: index]
                else:
                    sublist = self.allocations_list[i][index_first_not_completed: index + 1]
                sublist.append(relay_points[i])
                trace_list = [relay_points[j] for j in range(i)]
                if len([j for j in sublist if j.index == (-2, -2)]) == 2:
                    raise ValueError
                self.drones[i].path = sublist
                self.drones[i].path_copy = sublist[:]
                self.drones[i].relay_trace = list(reversed(trace_list))
        except:
            raise
        z = 1

    def loop(self):
        Constants.global_sync_time = 0
        self.t1 = time.time()
        time.sleep(0.1)
        last_t = time.time()
        f = True
        # generate relay points
        relay_time = Constants.relay_time
        try:
            self.near_blocks, self.relay_points = self.generate_relay(relay_time)
            self.process_relay(self.near_blocks, self.relay_points, relay_time)
        except ValueError:
            for dr in self.drones:
                dr.path = [GridBlock(Vector2D(-1, -1), Constants.server_loc, (0, 0, 0)), ]
                dr.state = DroneState.RTL

        for drone in self.drones:
            if len(drone.path) > 1:
                drone.state = DroneState.MOVING

        wasted_dt = 0
        while True:
            dt = time.time() - self.t1 #- wasted_dt/2
            self.t1 = time.time()
            Constants.global_sync_time += dt

            if f:
                wasted_dt = time.time()
                Constants.renderer.render_grid(self.blocks)
                wasted_dt = time.time() - wasted_dt
                #f = False

            # draw relay and gridpoints
            Constants.renderer.render_points([[r.loc, (0, 0, 0)] for r in self.near_blocks if not r is None])
            Constants.renderer.render_points([[l, (255, 255, 255)] for l in self.relay_points if not l is None])



            # update drones
            for drone in self.drones:
                drone.update(dt)

            curr_t = time.time()
            if curr_t - last_t > 5:
                image_send = Constants.renderer.output.copy()
                img = cv2.imencode(".jpg", image_send)[1]
                img_str = img.tostring()
                #Constants.chat_client.sendall(img_str)
                last_t = curr_t

            # Constants.flask_server.send(Constants.renderer.output)
            # image_send = Constants.renderer.output.copy()[:, :, [2, 1, 0]]
            # temp_img = cv2.imencode(".png", image_send)[1]
            # print(Utility.get_json_string("bg-img", img=temp_img))
            # Constants.renderer.show()
            # # testing send info
            # curr_t = time.time()
            # if curr_t - last_t > 5:
            #     if len(Constants.web_server_clients) > 0:
            #         drone_locs = [d.loc for d in self.drones]
            #         drone_data = Utility.get_json_string("drones", list_=drone_locs)
            #         relay_data = Utility.get_json_string("relay", list_=self.relay_points, next_est_relay=Constants.next_relay_time, drones=self.drones)
            #         grid_data = Utility.get_json_string("grid_data", list_=self.blocks)
            #         img_data = Utility.get_json_string("bg-img", list_=temp_img)
            #         # send data
            #         # if Constants.global_sync_time % 2 == 0:
            #         Constants.web_server_clients[-1].sendMessage(drone_data.encode('utf-8'))
            #         Constants.web_server_clients[-1].sendMessage(relay_data.encode('utf-8'))
            #         Constants.web_server_clients[-1].sendMessage(grid_data.encode('utf-8'))
            #         Constants.web_server_clients[-1].sendMessage(img_data.encode('utf-8'))
            #     curr_t = last_t
            Constants.renderer.show()

            # after drawing process relay
            if self.all_connected:
                self.process_relay_all_connected()

    def process_relay_all_connected(self):
        # Consider no drone dies #TODO Drone death XXX
        if not self.all_connected:
            return
        # TODO Do some important work and commands and stuff

        # Test
        print("Waiting for 2 at relay work for no reason at all")
        if Constants.global_sync_time - self.all_connected_time < 2:
            return
        # recompute relay
        relay_time = Constants.global_sync_time + Constants.relay_time
        Constants.next_relay_time = relay_time
        try:
            self.near_blocks, self.relay_points = self.generate_relay(relay_time)
            self.process_relay(self.near_blocks, self.relay_points, relay_time)
        except ValueError:
            for dr in self.drones:
                dr.path = [GridBlock(Vector2D(-1, -1), Constants.server_loc, (0, 0, 0)), ]
                dr.state = DroneState.RTL
                self.relay_points = []
                self.near_blocks = []
                self.connected_drones = []
            return

        self.connected_drones = []
        self.all_connected = False

        # continue
        for drone in self.drones:
            if len(drone.path) > 1:
                drone.state = DroneState.MOVING

    # Network functions
    def relay(self, drone_id, sender_id):
        drone = list(filter(lambda x: x.id == drone_id, self.drones))[0]
        drone.state = DroneState.UNDER_RELAY_CONNECTED
        self.connected_drones.append(drone)
        for d in self.drones:
            if d.state == DroneState.COMPLETED_WAITING:
                if not d in self.connected_drones:
                    self.connected_drones.append(d)

        if len(self.connected_drones) == Constants.num_drones:
            self.all_connected = True
            self.all_connected_time = Constants.global_sync_time
