import pymysql
import boto3
from datetime import datetime, timedelta
import time
import app
import logging
import math



#############
class AutoScalingManage:
    ec2 = boto3.client('ec2')
    elb = boto3.client('elbv2')
    s3 = boto3.client('s3')

    def new_ec2_instance(self):
        response = self.ec2.run_instances(
            ImageId=app.config.ami_id,
            InstanceType='t2.micro',
            MaxCount=1,
            MinCount=1,
            Monitoring={'Enabled':True},
            Placement={'AvailabilityZone':app.config.zone},
            SecurityGroupIds=[
                app.config.security_group,
            ],
            SubnetId=app.config.subnet_id,
            UserData='',
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags':[
                        {
                            'Key': 'Name',
                            'Value': app.config.InstanceName
                        },

                    ]
                },
            ],
            KeyName=app.config.keyname,

        )

        for instance in response['Instances']:
            print(instance['InstanceId']+'successfully created!')

        return response['Instances'][0]['InstanceId']

    def start_instance(self,InstanceId):
        self.ec2.start_instances(InstanceIds=[InstanceId])

    def stop_instance(self,InstanceId):
        self.ec2.stop_instances(InstanceIds=[InstanceId])

    def terminate_instance(self,InstanceId):
        self.ec2.terminate_instances(InstanceIds=[InstanceId])

    def stopped_instances(self):
        return self.ec2.describe_instances(Filters=[
                {'Name':'tag:Name','Values':[app.config.InstanceName]},
                {'Name':'instance-state-name', 'Values':['stopped']}
            ])

    def runnning_instances(self):
        return self.ec2.describe_instances(Filters=[
            {'Name': 'tag:Name', 'Values': [app.config.InstanceName]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ])

    def grow_worker(self):
        stopped_instances =self.stopped_instances()['Reservations']
        error=False
        if len(stopped_instances)>=1:
            new_instance_id=stopped_instances[0]['Instances'][0]['InstanceId']
            self.start_instance(new_instance_id)

        else:
            new_instance_id=self.new_ec2_instance()

        status=self.ec2.describe_instance_status(InstanceIds=[new_instance_id])

        while len(status['InstanceStatuses']) < 1:
            time.sleep(1)
            status = self.ec2.describe_instance_status(InstanceIds=[new_instance_id])
        while status['InstanceStatuses'][0]['InstanceState']['Name'] != 'running':
            time.sleep(1)
            status = self.ec2.describe_instance_status(InstanceIds=[new_instance_id])
        response = self.register_one_target(new_instance_id)
        return [error, '']

    def shrink_worker(self):
        #running_instances =self.runnning_instances()['Reservations']
        #shrink_instance_id= running_instances[0]['Instances'][0]['InstanceId']
        target_instances_id = self.get_valid_target_instance()
        error = False
        if len(target_instances_id) < 2:
            error = True
            return [error, 'No more worker to shrink!']
        else:
            self.stop_instance(target_instances_id[0])
            self.deregister_one_target(target_instances_id[0])
            return [error, '']


    def register_one_target(self,InstanceId):
        #target_group_arn = app.config.target_group_arn
        response =  self.elb.register_targets(
            TargetGroupArn = app.config.target_group_arn,
            Targets = [
                {
                    'Id':InstanceId,
                    'Port':5000,
                },
            ]
        )
        return response

    def deregister_one_target(self,InstanceId):
        self.elb.deregister_targets(
            TargetGroupArn=app.config.target_group_arn,
            Targets=[
                {
                    'Id': InstanceId,
                    'Port': 5000,
                },
            ]
        )

    def get_valid_target_instance(self):
        target_instances_id = []
        response = self.elb.describe_target_health(
            TargetGroupArn = app.config.target_group_arn,
        )
        if 'TargetHealthDescriptions' in response:
            for target in response['TargetHealthDescriptions']:
                if target['TargetHealth']['State'] != 'draining':
                    target_instances_id.append(target['Target']['Id'])
        return target_instances_id

    def get_all_target_instance(self):
        target_instances_id = []
        response = self.elb.describe_target_health(
            TargetGroupArn=app.config.target_group_arn,
        )
        if 'TargetHealthDescriptions' in response:
            for target in response['TargetHealthDescriptions']:
                if target['TargetHealth']['State'] != 'unhealthy':
                    target_instances_id.append(target['Target']['Id'])
            return target_instances_id

    def get_instance_state(self,InstanceId):
        return self.ec2.describe_instance_status(InstanceIds=[InstanceId])


############################
    def get_autoscaling_params(self):
        # CPU threshold for growing workers
        # CPU threshold for shrinking workers
        # expading ratio
        # shrinking ratio
        params = (80, 20, 2.00, 2.00)
        return params

    def get_time(self):
        end_time = datetime.datetime.utcnow().isoformat()
        start_time = (end_time - datetime.timedelta(minutes=2)).isoformat()
        return start_time, end_time

    def get_cpu_utils(self):
        ec2 = boto3.client('ec2')
        elb = boto3.client('elbv2')
        cloudwatch = boto3.client('cloudwatch')

        record = self.get_autoscaling_params()
        metric_name = 'CPUUtilization'
        namespace = 'AWS/EC2'
        statistic = 'Average'  # could be Sum,Maximum,Minimum,SampleCount,Average

        autoscaling_manage = AutoScalingManage()
        #target_instances_ids = autoscaling_manage.get_all_target_instance()
        target_instances_ids = autoscaling_manage.get_valid_target_instance()

        num_targets = 0
        cpu_util_sum = 0
        cpu_util_avg = 0
        logging.warning('all_target_instances_id: {}'.format(target_instances_ids))
        #start_time, end_time = self.get_time()

        for target in target_instances_ids:
            instance_id = target
            cpu = cloudwatch.get_metric_statistics(
                Period=1 * 60,
                StartTime=datetime.utcnow() - timedelta(seconds=2 * 60),
                EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
                MetricName=metric_name,
                Namespace=namespace,  # Unit='Percent',
                Statistics=[statistic],
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}]
            )
            print("instance id: ", instance_id)
            print("cpu utils: ", cpu)
            try:
                cpu_util_sum += cpu['Datapoints'][0]['Average']
                num_targets += 1
            except IndexError:
                pass
            # num_targets += 1

        print("average cpu: ", cpu_util_sum/num_targets)

        if num_targets:
            return cpu_util_sum/num_targets
        return 0

    #def start_multi_instances(self):

"""
    def grow_workers_by_ratio(self, ratio):
        current_targets_num = len(self.get_valid_target_instance())
        grow_targets_num = math.ceil(current_targets_num * (ratio - 1))
        expected_targets_num = current_targets_num  + grow_targets_num
        error = False
        stopped_instances = self.stopped_instances()['Reservation']
        stopped_instances_num = len(stopped_instances)

        if current_targets_num>=10:
            error = True
            return [error, "Reach worker pool limit"]
        if expected_targets_num > 10:
            #error = True
            grow_targets_num = 10 - current_targets_num

        if stopped_instances_num>=1:
            if stopped_instances_num >= grow_targets_num:
                new_instances_id = []
                for i in range(stopped_instances_num):
                    new_instances_id.append(stopped_instances[i]['Instances'][0]['InstancesId'])#why
                self.ec2.start_instances(InstanceIds=new_instances_id)
                status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)

                while len(status['InstanceStatuses']) < len(new_instances_id):
                    time.sleep(1)
                    status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)
                for i in range(len(new_instances_id)):
                    while status['InstanceStatuses'][i]['InstanceState']['Name'] != 'running':
                        time.sleep(1)
                        status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)
                    response = self.register_one_target(new_instances_id)
                for id in range(new_instances_id):
                    self.register_one_target(id)

            else: #stopped_instances<grow_targets_num
                new_instances_id = []
                for i in range(stopped_instances_num):
                    new_instances_id.append(stopped_instances_num[i]['Instances'][0]['InstancesId'])
                self.ec2.start_instances(InstanceIds=new_instances_id)

                rest_num = grow_targets_num- len(stopped_instances_num)

                for i in range(rest_num):
                    new_id = self.new_ec2_instance()
                    new_instances_id.append(new_id)

                status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)

                while len(status['InstanceStatuses']) < len(new_instances_id):
                    time.sleep(1)
                    status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)
                for i in range(len(new_instances_id)):
                    while status['InstanceStatuses'][i]['InstanceState']['Name'] != 'running':
                        time.sleep(1)
                        status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)
                    response = self.register_one_target(new_instances_id)
                for id in range(new_instances_id):
                    self.register_one_target(id)

        else:#no stopped instance
            new_instances_id = []
            for i in range(grow_targets_num):
                new_id = self.new_ec2_instance()
                new_instances_id.append(new_id)

            status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)

            while len(status['InstanceStatuses']) < len(new_instances_id):
                time.sleep(1)
                status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)
            for i in range(len(new_instances_id)):
                while status['InstanceStatuses'][i]['InstanceState']['Name'] != 'running':
                    time.sleep(1)
                    status = self.ec2.describe_instance_status(InstanceIds=new_instances_id)
                response = self.register_one_target(new_instances_id)
            for id in range(new_instances_id):
                self.register_one_target(id)
        return [error,'']


    def shrink_workers_by_ratio(self,ratio):
        current_targets_id = self.get_valid_target_instance()
        current_targets_num = len(current_targets_id)  # current_targets_ids
        expected_targets_num = math.floor(len(current_targets_num) * ratio)
        shrink_targets_num = current_targets_num - expected_targets_num
        error = False
        if current_targets_num <= 1:
            error =True
            return [error,'No more worker to shrink']
        if expected_targets_num <= 1:
            shrink_targets_num = current_targets_num - 1

        for i in range(shrink_targets_num):
            self.deregister_one_target(InstanceId=current_targets_id[i])
            self.ec2.stop_instances(InstanceIds=current_targets_num[i])
            time.sleep(1)

        return [error,'']
        
"""







"""
    def grow_workers_by_ratio(self,ratio):
        #ratio = 2
        current_targets = self.get_valid_target_instance()
        grow_targets_num = math.ceil(len(current_targets) * (ratio - 1))
        expected_targets_num = current_targets + grow_targets_num
        error = False

        if ratio<=1:
            error = True
            return [error, "Invalid ratio. Please enter ratio > 1"]

        if len(current_targets) == 10:
            error = True
            return [error, "Worker pool size limit is reached"]
        if len(current_targets)<1:
            error = True
            return [error, "No target in target group"]
        if expected_targets_num > 10 :
            grow_targets_num = 10 - len(current_targets)

        for i in range(grow_targets_num):
            self.grow_worker()
        return [error,'']


    def shrink_workers_by_ratio(self,ratio):
        current_targets = self.get_valid_target_instance()#current_targets_ids
        expected_targets_num = math.floor(len(current_targets) * ratio)
        error = False
        if ratio > 1:
            error = True
            return [error, 'Shrink ratio should be less than 1']
        elif len(current_targets) == 10:
            error = True
            return [error, "Worker pool size limit is reached"]
        elif len(current_targets)< 2:
            error = True
            return [error, "No more worker to shrink "]
        elif expected_targets_num <=1 :
            #shrink_targets_num = current_targets - expected_targets_num
            expected_targets_num = 1
            shrink_targets_num = len(current_targets) - expected_targets_num
        else:
            shrink_targets_num = len(current_targets) - expected_targets_num

        if shrink_targets_num:
            for i in range(shrink_targets_num):
                self.shrink_worker()

        return [error, '']

"""








