"""Keep Rutgers Slurm and explicitly authorized dedicated-host execution distinct."""
import json
import os
import socket


def validate_context():
    mode = os.environ.get('OPENARMS_EXECUTION_CONTEXT', 'slurm')
    hostname = socket.gethostname()
    fqdn = socket.getfqdn()
    if mode == 'slurm':
        if not os.environ.get('SLURM_JOB_ID'):
            raise RuntimeError('Rutgers execution requires an allocated Slurm job')
    elif mode == 'dedicated':
        if hostname != os.environ.get('OPENARMS_DEDICATED_HOST'):
            raise RuntimeError('Dedicated host must exactly match the authorized hostname')
        if fqdn.endswith('.rutgers.edu') or hostname.split('.')[0].startswith(('ilab', 'rlab')):
            raise RuntimeError('Rutgers managed nodes must use Slurm')
    else:
        raise RuntimeError('Unknown execution context')
    return {'mode': mode, 'hostname': hostname, 'fqdn': fqdn,
            'slurm_job_id': os.environ.get('SLURM_JOB_ID')}


if __name__ == '__main__':
    print(json.dumps(validate_context()))
