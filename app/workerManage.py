import boto3
import time

from flask import current_app


class WorkerManage:
    ec2 = boto3.client('ec2')
    elb = boto3.client('elbv2')
    s3 = boto3.client('s3')

    def new_ec2_instance(self):
        response = self.ec2.run_instances(
            ImageId='ami_id',
            InstanceType='t2.micro',
            MaxCount=1,
            MinCount=1,
            Monitoring={'enabled':True},
            Placement={'AvailabilityZone':current_app.config.zone},
            SecurityGroupIds=[
                current_app.config.security_group,
            ],
            SubnetId=current_app.config.subnet_id,
            UserData='',
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags':[
                        {
                            'Key': 'Name',
                            'Value': current_app.config.instance_name
                        },

                    ]
                },
            ],
            KeyName=current_app.config.keyname,

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
                {'Name':'Tag:Name','Values':[current_app.config.instance_name]},
                {'Name':'instance-state-name', 'Values':['stopped']}
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
        #self.register_target(new_instance_id)
        return [error, '']

    def shrink_worker(self,InstanceId):
        error = False
        if len(InstanceId) < 1:
            error = True
            return [error, 'No more worker to shrink!']
        else:
            self.stop_instance(InstanceId)
            return [error, '']

