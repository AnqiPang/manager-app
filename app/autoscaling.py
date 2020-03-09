import pymysql
import boto3
import datetime
import time
import app
import logging



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
        self.register_one_target(new_instance_id)
        return [error, '']

    def shrink_worker(self):
        #running_instances =self.runnning_instances()['Reservations']
        #shrink_instance_id= running_instances[0]['Instances'][0]['InstanceId']
        target_instances_id = self.get_valid_target_instance()
        error = False
        if len(target_instances_id) < 1:
            error = True
            return [error, 'No more worker to shrink!']
        else:
            self.stop_instance(target_instances_id[0])
            self.deregister_one_target(target_instances_id[0])
            return [error, '']


    def register_one_target(self,InstanceId):
        #target_group_arn = app.config.target_group_arn
        self.elb.register_targets(
            TargetGroupArn = app.config.target_group_arn,
            Targets = [
                {
                    'Id':InstanceId,
                    'Port':5000,
                },
            ]
        )

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
        target_instances_ids = autoscaling_manage.get_all_target_instance()
        num_targets = 0
        cpu_util_sum = 0
        logging.warning('all_target_instances_id: {}'.format(target_instances_ids))
        start_time, end_time = self.get_time()

        for target in target_instances_ids:
            instance_id = target
            cpu = cloudwatch.get_metric_statistics(
                Period=1 * 60,
                StartTime=start_time,
                EndTime=end_time,
                MetricName=metric_name,
                Namespace=namespace,  # Unit='Percent',
                Statistics=[statistic],
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}]
            )
            print(cpu)
            try:
                cpu_util_sum += cpu['Datapoints'][0]['Average']
                num_targets += 1
            except IndexError:
                pass
            # num_targets += 1

            return cpu_util_sum / num_targets









