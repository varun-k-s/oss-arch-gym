import os
import sys

import json
import numpy as np

from absl import flags
from absl import app
from absl import logging
os.sys.path.insert(0, os.path.abspath('../../'))
os.sys.path.insert(0, os.path.abspath('../../arch_gym'))
from sko.GA import GA
from configs import arch_gym_configs
from arch_gym.envs.envHelpers import helpers
from arch_gym.envs import AstraSimWrapper
import envlogger

from configs import arch_gym_configs

import pandas as pd
import matplotlib.pyplot as plt

flags.DEFINE_integer('num_steps', 20, 'Number of training steps.')
flags.DEFINE_integer('num_agents', 4, 'Number of agents.')
flags.DEFINE_float('prob_mutation', 0.1, 'Probability of mutation.')
flags.DEFINE_string('workload','resnet18', 'ML model name')
flags.DEFINE_integer('layer_id', 2, 'Layer id')
flags.DEFINE_string('summary_dir', 'test', 'Directory to save the summary.')
flags.DEFINE_string('reward_formulation', 'latency', 'Reward formulation to use')
flags.DEFINE_string('traject_dir','ga_trajectories', 'Directory to save the dataset.')
flags.DEFINE_bool('use_envlogger', True, 'Whether to use envlogger.')

FLAGS = flags.FLAGS

# define AstraSim version
VERSION = 1

# define helpers
astraSim_helper = helpers()

def generate_run_directories():
    # Construct the exp name from seed and num_iter
    exp_name = FLAGS.workload + "_num_iter_" + str(FLAGS.num_steps) + "_num_agents_" + str(FLAGS.num_agents) + "_prob_mut_" + str(FLAGS.prob_mutation)
  
    traject_dir = os.path.join(FLAGS.summary_dir, FLAGS.traject_dir, FLAGS.reward_formulation, exp_name)
    
    # log directories for storing exp csvs
    exp_log_dir = os.path.join(FLAGS.summary_dir,"ga_logs",FLAGS.reward_formulation, exp_name)

    return traject_dir, exp_log_dir


def log_fitness_to_csv(filename, fitness_dict):
        df = pd.DataFrame([fitness_dict['reward']])
        csvfile = os.path.join(filename, "fitness.csv")
        df.to_csv(csvfile, index=False, header=False, mode='a')

        df = pd.DataFrame([fitness_dict['action']])
        csvfile = os.path.join(filename, "actions.csv")
        df.to_csv(csvfile, index=False, header=False, mode='a')


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

def AstraSim_optimization_function(p):
    settings_file_path = os.path.realpath(__file__)
    settings_dir_path = os.path.dirname(settings_file_path)
    proj_root_path = os.path.abspath(settings_dir_path)

    astrasim_archgym = os.path.join(proj_root_path, "astrasim-archgym")
    archgen_v1_knobs = os.path.join(astrasim_archgym, "dse/archgen_v1_knobs")
    knobs_spec = os.path.join(archgen_v1_knobs, "archgen_v1_knobs_spec.py")

    networks_folder = os.path.join(astrasim_archgym, "themis/inputs/network")
    systems_folder = os.path.join(astrasim_archgym, "themis/inputs/system")
    workloads_folder = os.path.join(astrasim_archgym, "themis/inputs/workload")

    # DEFINE NETWORK AND SYSTEM AND WORKLOAD
    network_file = os.path.join(networks_folder, "analytical/4d_ring_fc_ring_switch.json")
    system_file = os.path.join(systems_folder, "4d_ring_fc_ring_switch_baseline.txt")
    workload_file = os.path.join(workloads_folder, "all_reduce/allreduce_0.65.txt")
    
    env = AstraSimWrapper.make_astraSim_env(rl_form='random_walker')
    fitness_hist = {}

    traject_dir, exp_log_dir = generate_run_directories()
    
    # check if log_path exists else create it
    if not os.path.exists(exp_log_dir):
        os.makedirs(exp_log_dir)

    if FLAGS.use_envlogger:
        if not os.path.exists(traject_dir):
            os.makedirs(traject_dir)
            
    env = wrap_in_envlogger(env, traject_dir)
    
    # reset the environment
    env.reset()

    # decode the actions
    system_knob, network_knob, workload_knob = astraSim_helper.parse_knobs_astrasim(knobs_spec)

    action_dict = {}
    action_dict['workload'] = {"path": workload_file}
    
    # parse system and network
    action_dict['system'] = astraSim_helper.parse_system_astrasim(system_file, action_dict, VERSION)
    action_dict['network'] = astraSim_helper.parse_network_astrasim(network_file, action_dict, VERSION)
    dimension = action_dict['network']['dimensions-count']

    action_dict_decoded = astraSim_helper.action_decoder_ga_astraSim(p, system_knob, network_knob, workload_knob, dimension)
    
    # change all variables decoded into action_dict
    for sect in action_dict_decoded:
        for key in action_dict_decoded[sect]:
            action_dict[sect][key] = action_dict_decoded[sect][key]

    # take a step
    step_type, reward, discount, info = env.step(action_dict)
    
    fitness_dict = {}
    fitness_dict["action"] = p
    fitness_dict["reward"] = reward
    fitness_dict["obs"] = info

    # Convert dictionary to dataframe
    fitness_df = pd.DataFrame([fitness_dict], columns=["action", "reward", "obs"])

    # check if exp_log_dir exists
    if not os.path.exists(exp_log_dir):
        os.makedirs(exp_log_dir)

    # write it to csv file append mode
    fitness_df.to_csv(os.path.join(exp_log_dir, "fitness.csv"), mode='a', header=False, index=False)
    
    
    return -1 * reward

def generate_bounds(action_dict, knobs_spec):
    # parse knobs
    system_knob, network_knob, workload_knob = astraSim_helper.parse_knobs_astrasim(knobs_spec)
    dicts = [system_knob, network_knob, workload_knob]

    # ASSUMES dimension is specified by input files (otherwise randomized)
    if "dimensions-count" in system_knob.keys():
        action_dict['network']["dimensions-count"] = random.choice(network_knob["dimensions-count"])
        dimension = action_dict['network']["dimensions-count"]
        system_knob.remove("dimensions-count")
    else:
        dimension = action_dict['network']["dimensions-count"]

    # initialize lower and upper bounds and precision
    lb, ub, precision = [], [], []
    for dict_type in dicts:
        knobs = dict_type.keys()
        for knob in knobs:
            if isinstance(dict_type[knob][0], set):
                if dict_type[knob][1] == "FALSE":
                    lb += [0] * dimension
                    ub += [len(dict_type[knob][0])-1] * dimension
                    precision += [1] * dimension
                else:
                    lb += [0]
                    ub += [len(dict_type[knob][0])-1]
                    precision += [1]
            else:
                if dict_type[knob][1] == "FALSE":
                    lb += [dict_type[knob][0][0]] * dimension
                    ub += [dict_type[knob][0][1]] * dimension
                    precision += [dict_type[knob][0][2]] * dimension 
                else:
                    lb += [dict_type[knob][0][0]]
                    ub += [dict_type[knob][0][1]]
                    precision += [dict_type[knob][0][2]]

    return lb, ub, precision


def main(_):
    
    workload = FLAGS.workload
    layer_id = FLAGS.layer_id

    settings_file_path = os.path.realpath(__file__)
    settings_dir_path = os.path.dirname(settings_file_path)
    proj_root_path = os.path.abspath(settings_dir_path)

    astrasim_archgym = os.path.join(proj_root_path, "astrasim-archgym")
    archgen_v1_knobs = os.path.join(astrasim_archgym, "dse/archgen_v1_knobs")
    knobs_spec = os.path.join(archgen_v1_knobs, "archgen_v1_knobs_spec.py")

    networks_folder = os.path.join(astrasim_archgym, "themis/inputs/network")
    network_file = os.path.join(networks_folder, "analytical/4d_ring_fc_ring_switch.json")

    action_dict = {}
    action_dict['network'] = astraSim_helper.parse_network_astrasim(network_file, action_dict, VERSION)
    lower_bound, upper_bound, precision = generate_bounds(action_dict, knobs_spec)

    # encoding format: bounds have same order as modified parameters file
    ga = GA(
        func=AstraSim_optimization_function,
        n_dim=len(lower_bound), 
        size_pop=FLAGS.num_agents,
        max_iter=FLAGS.num_steps,
        prob_mut=FLAGS.prob_mutation,
        lb=lower_bound, 
        ub=upper_bound,
        precision=precision,
    )

    """
    "scheduling-policy": {"FIFO", "LIFO"},
    "collective-optimization": {"localBWAware", "baseline"},
    "intra-dimension-scheduling": {"FIFO", "SCF"},
    "inter-dimension-scheduling": {"baseline", "themis"}
    """
    
    best_x, best_y = ga.run()
    
    
    # get directory names
    _, exp_log_dir = generate_run_directories()
    
    # check if exp_log_dir exists
    if not os.path.exists(exp_log_dir):
        os.makedirs(exp_log_dir)
    
    print(ga.all_history_Y)
    # Convert each array to a list and concatenate the resulting lists
    arr = [a.squeeze().tolist() for a in ga.all_history_Y]

    print(arr)
    
    Y_history = pd.DataFrame(arr)
    Y_history.to_csv(os.path.join(exp_log_dir, "Y_history.csv"))

    fig, ax = plt.subplots(2, 1)
    ax[0].plot(Y_history.index, Y_history.values, '.', color='red')
    Y_history.min(axis=1).cummin().plot(kind='line')
    plt.savefig(os.path.join(exp_log_dir, "Y_history.png"))
    
    # save the best_x and best_y to a csv file
    best_x = pd.DataFrame(best_x)
    best_x.to_csv(os.path.join(exp_log_dir, "best_x.csv"))

    best_y = pd.DataFrame(best_y)
    best_y.to_csv(os.path.join(exp_log_dir, "best_y.csv"))


if __name__ == '__main__':
   app.run(main)
