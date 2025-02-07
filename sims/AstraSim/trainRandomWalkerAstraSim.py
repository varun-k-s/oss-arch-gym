import json
import time
import random
import pandas as pd
import numpy as np
import envlogger
import os
import sys
os.sys.path.insert(0, os.path.abspath('../../'))
os.sys.path.insert(0, os.path.abspath('../../arch_gym'))
from arch_gym.envs import AstraSimWrapper, AstraSimEnv
from arch_gym.envs.envHelpers import helpers
from configs import arch_gym_configs

from absl import flags
from absl import app
from absl import logging


# define workload in run_general.sh
flags.DEFINE_string('workload', 'resnet18', 'Which AstraSim workload to run?')
flags.DEFINE_integer('num_steps', 50, 'Number of training steps.')
flags.DEFINE_integer('num_episodes', 1, 'Number of training episodes.')
flags.DEFINE_bool('use_envlogger', True, 'Use envlogger to log the data.')
flags.DEFINE_string('traject_dir',
                    'random_walker_trajectories',
                    'Directory to save the dataset.')
flags.DEFINE_string('summary_dir', ".", 'Directory to save the dataset.')
flags.DEFINE_string('reward_formulation', 'latency',
                    'Which reward formulation to use?')
FLAGS = flags.FLAGS

# define AstraSim version
VERSION = 1

# action_type = specify 'network' or 'system
# new_params = parsed knobs from experiment file
def generate_random_actions(action_dict, system_knob, network_knob, workload_knob):
    dicts = [(system_knob, 'system'), (network_knob, 'network'), (workload_knob, 'workload')]
    if "dimensions-count" in system_knob.keys():
        action_dict['network']["dimensions-count"] = random.choice(network_knob["dimensions-count"])
        dimension = action_dict['network']["dimensions-count"]
        system_knob.remove("dimensions-count")
    else:
        dimension = action_dict['network']["dimensions-count"]

    for dict_type, dict_name in dicts:
        knobs = dict_type.keys()
        for knob in knobs:
            if isinstance(dict_type[knob][0], set):
                if dict_type[knob][1] == "FALSE":
                    action_dict[dict_name][knob] = [random.choice(
                        list(dict_type[knob][0])) for _ in range(dimension)]
                elif dict_type[knob][1] == "TRUE":
                    choice = random.choice(list(dict_type[knob][0]))
                    action_dict[dict_name][knob] = [choice for _ in range(dimension)]
                else:
                    action_dict[dict_name][knob] = random.choice(
                        list(dict_type[knob][0]))
            else:
                if dict_type[knob][1] == "FALSE":
                    action_dict[dict_name][knob] = [random.randint(
                        dict_type[knob][0][0], dict_type[knob][0][1]) for _ in range(dimension)]
                elif dict_type[knob][1] == "TRUE":
                    choice = random.randint(dict_type[knob][0][0], dict_type[knob][0][1])
                    action_dict[dict_name][knob] = [choice for _ in range(dimension)]
                else:
                    action_dict[dict_name][knob] = random.randint(
                        dict_type[knob][0][0], dict_type[knob][0][1])

    return action_dict


def log_results_to_csv(filename, fitness_dict):
    df = pd.DataFrame([fitness_dict['reward']])
    csvfile = os.path.join(filename, "rewards.csv")
    df.to_csv(csvfile, index=False, header=False, mode='a')

    df = pd.DataFrame([fitness_dict['action']])
    csvfile = os.path.join(filename, "actions.csv")
    df.to_csv(csvfile, index=False, header=False, mode='a')

    df = pd.DataFrame([fitness_dict['obs']])
    csvfile = os.path.join(filename, "observations.csv")
    df.to_csv(csvfile, index=False, header=False, mode='a')


# Random walker then random walker, else use other
def wrap_in_envlogger(env, envlogger_dir):
    metadata = {
        'agent_type': 'RandomWalker',
        'num_steps': FLAGS.num_steps,
        'env_type': type(env).__name__,
    }
    if FLAGS.use_envlogger:
        logging.info('Wrapping environment with EnvironmentLogger...')
        env = envlogger.EnvLogger(env,
                                  data_directory=envlogger_dir,
                                  max_episodes_per_file=1000,
                                  metadata=metadata)
        logging.info('Done wrapping environment with EnvironmentLogger.')
        return env
    else:
        return env


def main(_):
    settings_file_path = os.path.realpath(__file__)
    settings_dir_path = os.path.dirname(settings_file_path)
    proj_root_path = os.path.abspath(settings_dir_path)
    astrasim_archgym = os.path.join(proj_root_path, "astrasim-archgym")

    # TODO: V1 SPEC:
    archgen_v1_knobs = os.path.join(astrasim_archgym, "dse/archgen_v1_knobs")
    knobs_spec = os.path.join(archgen_v1_knobs, "archgen_v1_knobs_spec.py")
    networks_folder = os.path.join(archgen_v1_knobs, "templates/network")
    systems_folder = os.path.join(astrasim_archgym, "themis/inputs/system")
    workloads_folder = os.path.join(astrasim_archgym, "themis/inputs/workload")

    # DEFINE NETWORK AND SYSTEM AND WORKLOAD
    network_file = os.path.join(networks_folder, "4d_ring_fc_ring_switch.json")
    system_file = os.path.join(
        systems_folder, "4d_ring_fc_ring_switch_baseline.txt")
    workload_file = os.path.join(workloads_folder, "all_reduce/allreduce_0.65.txt")

    exe_path = os.path.join(proj_root_path, "run_general.sh")
    network_config = os.path.join(proj_root_path, "general_network.json")
    system_config = os.path.join(proj_root_path, "general_system.txt")
    workload_config = os.path.join(proj_root_path, "general_workload.txt")

    env = AstraSimWrapper.make_astraSim_env(rl_form='random_walker')
    # env = AstraSimEnv.AstraSimEnv(rl_form='random_walker')

    astrasim_helper = helpers()

    # experiment name
    exp_name = str(FLAGS.workload)+"_num_steps_" + \
        str(FLAGS.num_steps) + "_num_episodes_" + str(FLAGS.num_episodes)
    # append logs to base path
    log_path = os.path.join(
        FLAGS.summary_dir, 'random_walker_logs', FLAGS.reward_formulation, exp_name)
    # get the current working directory and append the exp name
    traject_dir = os.path.join(
        FLAGS.summary_dir, FLAGS.traject_dir, FLAGS.reward_formulation, exp_name)
    # check if log_path exists else create it
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    if FLAGS.use_envlogger:
        if not os.path.exists(traject_dir):
            os.makedirs(traject_dir)
    env = wrap_in_envlogger(env, traject_dir)

    start = time.time()

    step_results = {}

    # INITIATE action dict
    action_dict = {}

    # if path exists, use path, else parse the sub-dict
    action_dict['workload'] = {"path": workload_file}

    # parse system and network
    action_dict['system'] = astrasim_helper.parse_system_astrasim(system_file, action_dict, VERSION)
    action_dict['network'] = astrasim_helper.parse_network_astrasim(network_file, action_dict, VERSION)

    # parse knobs
    system_knob, network_knob, workload_knob = astrasim_helper.parse_knobs_astrasim(knobs_spec)

    best_reward, best_observation, best_actions = 0.0, 0.0, {}

    for i in range(FLAGS.num_episodes):
        logging.info('Episode %r', i)

        for step in range(FLAGS.num_steps):
            # pass into generate_random_actions(dimension, knobs)
            action_dict = generate_random_actions(action_dict, system_knob, network_knob, workload_knob)

            # with open("general_workload.txt", 'w') as file:
            #     file.write(action["workload"]["value"])

            # step_result wrapped in TimeStep object
            step_result = env.step(action_dict)
            step_type, reward, discount, observation = step_result

            step_results['reward'] = [reward]
            step_results['action'] = action_dict
            step_results['obs'] = observation

            if reward and reward > best_reward:
                best_reward = reward
                best_observation = observation
                best_actions = action_dict

            log_results_to_csv(log_path, step_results)

    end = time.time()

    print("Best Reward: ", best_reward)
    print("Best Observation: ", best_observation)
    print("Best Parameters: ", best_actions)
    print("Total Time Taken: ", end - start)
    print("Total Useful Steps: ", env.useful_counter)


if __name__ == '__main__':
    app.run(main)
