from __future__ import print_function

import argparse
import os
import shutil
import time
import random
import sys
import optuna
import numpy as np
import warnings
warnings.filterwarnings("ignore")

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torch.utils.data as data
import torchvision.transforms as transforms
import torchvision.datasets as datasets
import torchvision.models as models
import models.classification as customized_models
from torchsummary import summary
from datasets import list_dataset
import moco.loader

from pytorch_grad_cam import HiResCAM, FullGrad, XGradCAM
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget
from pytorch_grad_cam.utils.image import show_cam_on_image

from utils import Bar, Logger, AverageMeter, accuracy, mkdir_p, savefig, ProgressMeter

# Models
default_model_names = sorted(name for name in models.__dict__
    if name.islower() and not name.startswith("__")
    and callable(models.__dict__[name]))



customized_models_names = sorted(name for name in customized_models.__dict__
    if name.islower() and not name.startswith("__")
    and callable(customized_models.__dict__[name]))
#print(customized_models_names)
for name in customized_models.__dict__:
    if name.islower() and not name.startswith("__") and callable(customized_models.__dict__[name]):
        models.__dict__[name] = customized_models.__dict__[name]

model_names = default_model_names + customized_models_names

# Parse arguments
parser = argparse.ArgumentParser(description='PyTorch Class Training')

# Datasets
parser.add_argument('-d', '--data', default='path to dataset', type=str)
parser.add_argument('--optuna_study_db', default='path to optuna study db', type=str)
parser.add_argument('-j', '--workers', default=8, type=int, metavar='N',
                    help='number of data loading workers (default: 8)')
# Optimization options
parser.add_argument('--epochs', default=90, type=int, metavar='N',
                    help='number of total epochs to run')
parser.add_argument('--start-epoch', default=0, type=int, metavar='N',
                    help='manual epoch number (useful on restarts)')
parser.add_argument('--train-batch', default=256, type=int, metavar='N',
                    help='train batchsize (default: 256)')
parser.add_argument('--test-batch', default=200, type=int, metavar='N',
                    help='test batchsize (default: 200)')
parser.add_argument('--lr', '--learning-rate', default=0.1, type=float,
                    metavar='LR', help='initial learning rate')
parser.add_argument('--drop', '--dropout', default=0, type=float,
                    metavar='Dropout', help='Dropout ratio')
parser.add_argument('--schedule', type=int, nargs='+', default=[150, 225],
                        help='Decrease learning rate at these epochs.')
parser.add_argument('--gamma', type=float, default=0.1, help='LR is multiplied by gamma on schedule.')
parser.add_argument('--momentum', default=0.9, type=float, metavar='M',
                    help='momentum')
parser.add_argument('--weight-decay', '--wd', default=1e-4, type=float,
                    metavar='W', help='weight decay (default: 1e-4)')
# Checkpoints
parser.add_argument('-c', '--checkpoint', default='checkpoints', type=str, metavar='PATH',
                    help='path to save checkpoint (default: checkpoints)')
parser.add_argument('--resume', default='', type=str, metavar='PATH',
                    help='path to latest checkpoint (default: none)')
parser.add_argument('--weights_load', default='', type=str, metavar='PATH',
                    help='path to weights of backboim_splitne (default: none)')
# Architecture
parser.add_argument('--arch', '-a', metavar='ARCH', default='resnet18',
                    choices=model_names,
                    help='model architecture: ' +
                        ' | '.join(model_names) +
                        ' (default: resnet18)')
parser.add_argument('--depth', type=int, default=29, help='Model depth.')
parser.add_argument('--cardinality', type=int, default=32, help='ResNet cardinality (group).')
parser.add_argument('--base-width', type=int, default=4, help='ResNet base width.')
parser.add_argument('--widen-factor', type=int, default=4, help='Widen factor. 4 -> 64, 8 -> 128, ...')
# Miscs
parser.add_argument('--manualSeed', type=int, help='manual seed')
parser.add_argument('-e', '--evaluate', dest='evaluate', action='store_true',
                    help='evaluate model on validation set')
parser.add_argument('--pretrained', dest='pretrained', action='store_true',
                    help='use pre-trained model')
#Device options
parser.add_argument('--gpu-id', default='0', type=str,
                    help='id(s) for CUDA_VISIBLE_DEVICES')

args = parser.parse_args()
state = {k: v for k, v in args._get_kwargs()}

# Use CUDA
os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu_id
use_cuda = torch.cuda.is_available()

# Random seed
if args.manualSeed is None:
    args.manualSeed = random.randint(1, 10000)
random.seed(args.manualSeed)
torch.manual_seed(args.manualSeed)
if use_cuda:
    torch.cuda.manual_seed_all(args.manualSeed)



def main():
    

    if not os.path.isdir(args.checkpoint):
        mkdir_p(args.checkpoint)


		
    # Create optuna study object to tune hyperparameters
    study = optuna.create_study(study_name="Class_optuna_study", direction="maximize",storage=args.optuna_study_db,load_if_exists=True)
    study.optimize(objective, n_trials=100)

    # Get trials report
    pruned_trials = study.get_trials(deepcopy=False, states=[TrialState.PRUNED])
    complete_trials = study.get_trials(deepcopy=False, states=[TrialState.COMPLETE])

    print("Study statistics: ")
    print("  Number of finished trials: ", len(study.trials))
    print("  Number of pruned trials: ", len(pruned_trials))
    print("  Number of complete trials: ", len(complete_trials))

    print("Best trial:")
    trial = study.best_trial

    print("  Value: ", trial.value)
		
####### Model creation and optuna based training and testing
# ---------------------------------------------------------------
def objective(trial) :
    global best_acc
    best_acc = 0  # best test accuracy
    start_epoch = args.start_epoch  # start from epoch 0 or last checkpoint epoch
	
    # Data loading code
    base_path = '/mnt/sdb/datasets/MVOR_dataset/surgeons/'
    train_data = '/mnt/sdb/datasets/MVOR_dataset/surgeons/surg_train.txt'
    traindir = os.path.join(args.data, 'train')
    valdir = os.path.join(args.data, 'val')
    normalize = transforms.Normalize(mean=[0.5, 0.5, 0.5],
                                     std=[0.5, 0.5, 0.5])

    cam_transform = transforms.Compose([transforms.ToTensor(), transforms.Resize((256,256))])

    listdata=[]
    
    listdata.append(datasets.ImageFolder(traindir,
                           transform=transforms.Compose([
                           transforms.Resize((128,256)),
                           #transforms.RandomResizedCrop(size=(256,256), scale=(0.2, 1.)),
                           #transforms.RandomApply([
                           #    transforms.ColorJitter(0.4, 0.4, 0.4, 0.1)  # not strengthened
                           #], p=0.8),
                           #transforms.RandomGrayscale(p=0.2),
                           #transforms.RandomApply([moco.loader.GaussianBlur([.1, 2.])], p=0.5),
                           #transforms.RandomHorizontalFlip(),
                           transforms.RandAugment(),
                           #transforms.AugMix(),
                           transforms.ToTensor(),
                           normalize])))
    listdata.append(datasets.ImageFolder(traindir,
                           transform=transforms.Compose([
                           transforms.Resize((128,256)),
                           transforms.TrivialAugmentWide(),
                           transforms.ToTensor(),
                           normalize])))

                           
    val_dataset = datasets.ImageFolder(valdir,
                           transform=transforms.Compose([
                           transforms.Resize((128,256)),
                           transforms.ToTensor(),
                           normalize]))

    train_loader  = torch.utils.data.DataLoader(data.ConcatDataset(listdata), batch_size= args.train_batch, shuffle=True,
                                                num_workers=args.workers, drop_last=True, pin_memory=True) #  changed

    val_loader   = torch.utils.data.DataLoader(val_dataset, batch_size= args.test_batch, shuffle=False,
                                               num_workers=args.workers, drop_last=False, pin_memory=True) # test_batch

    # create model
    if args.pretrained:
        print("=> using pre-trained model '{}'".format(args.arch))
        model = models.__dict__[args.arch](pretrained=True)
    elif args.arch.startswith('resnext'):
        model = models.__dict__[args.arch](
                    baseWidth=args.base_width,
                    cardinality=args.cardinality,
                )
    elif args.arch.startswith('effnetv2'):

        model = models.__dict__[args.arch](
                    num_classes=82, width_mult=1.,
                )
    elif args.arch.startswith('vit'):

        model = models.__dict__[args.arch](
                    image_size = 480,
                    patch_size = 32,
                    num_classes = 8,
                    dim = 1024,
                    depth = 6,
                    heads = 16,
                    mlp_dim = 2048,
                    dropout = 0.1,
                    emb_dropout = 0.1
                    )
    else:
        print("=> creating model '{}'".format(args.arch))
        model = models.__dict__[args.arch]()

    if args.arch.startswith('alexnet') or args.arch.startswith('vgg'):
        model.features = torch.nn.DataParallel(model.features)
        model.cuda()
    else:
        model=model.cuda()


    cudnn.benchmark = True
    print('    Total params: %.2fM' % (sum(p.numel() for p in model.parameters())/1000000.0))
	
    # Tune hyperparameters(learning rate, weight decay and momentum) using optuna for best model
    lr = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
    weight_decay = trial.suggest_float("weight_decay", 1e-7, 1e-5, log=True)
    momentum = trial.suggest_float("momentum", 0.9, 0.95)

    # define loss function (criterion) and optimizer
    criterion = nn.CrossEntropyLoss().cuda()
    hm_criterion1 = nn.MSELoss(reduction='mean').cuda()
    hm_criterion2 = nn.MSELoss(reduction='mean').cuda()

    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=momentum, weight_decay=weight_decay)

    if args.weights_load:
        # Load checkpoint.
        print('==> Loading weights for backbone..')
        assert os.path.isfile(args.weights_load), 'Error: no checkpoint directory found!'
        checkpoint = torch.load(args.weights_load)
        best_acc = checkpoint['best_acc']
        best_acc = 0
        start_epoch = 0 
        model_dict = model.state_dict()
        
        pretrained_dict = checkpoint['state_dict']
        # 1. filter out unnecessary keys
        pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
        # 2. overwrite entries in the existing state dict
        model_dict.update(pretrained_dict) 
        # 3. load the new state dict
        model.load_state_dict(model_dict)
    # Resume
    title = 'Class-' + args.arch
    if args.resume:
        # Load checkpoint.
        print('==> Resuming from checkpoint..')
        assert os.path.isfile(args.resume), 'Error: no checkpoint directory found!'
        args.checkpoint = os.path.dirname(args.resume)
        checkpoint = torch.load(args.resume)
        best_acc = checkpoint['best_acc']
        best_acc = 0
        start_epoch = checkpoint['epoch']
        model.load_state_dict(checkpoint['state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer'])
        logger = Logger(os.path.join(args.checkpoint, 'log_'+str(trial.number)+'.txt'), title=title, resume=True)
    else:
        logger = Logger(os.path.join(args.checkpoint, 'log_'+str(trial.number)+'.txt'), title=title)
        logger.set_names(['Learning Rate', 'Train Loss', 'Valid Loss', 'Train Acc.', 'Valid Acc.', 'train_surg_ppe_top1_avg', 'test_surg_ppe_top1_avg'])


    if args.evaluate:
        print('\nEvaluation only')
        test_loss, test_acc = test(val_loader, model, criterion, start_epoch, use_cuda)
        print(' Test Loss:  %.8f, Test Acc:  %.2f' % (test_loss, test_acc))
        return

    # Train and val
    for epoch in range(start_epoch, args.epochs):
        #adjust_learning_rate(optimizer, epoch)
        print('\nTrial number %d, lr %.7f, momentum %.7f, weight_decay %.7f' % (trial.number, lr, momentum, weight_decay))

        print('Epoch: [%d | %d] LR: %f' % (epoch + 1, args.epochs, lr))

        train_loss, train_acc, train_surg_ppe_top1_avg = train(train_loader, model, criterion, hm_criterion1, hm_criterion2, cam_transform, optimizer, epoch, use_cuda)
        test_loss, test_acc, test_surg_ppe_top1_avg = test(val_loader, model, criterion, epoch, use_cuda)
        
        # append logger file
        logger.append([lr, train_loss, test_loss, train_acc, test_acc, train_surg_ppe_top1_avg, test_surg_ppe_top1_avg])

        # save model
        is_best = test_acc > best_acc
        best_acc = max(test_acc, best_acc)
        save_checkpoint({
                'epoch': epoch + 1,
                'state_dict': model.state_dict(),
                'acc': test_acc,
                'best_acc': best_acc,
                'train_acc': train_acc,
                'optimizer' : optimizer.state_dict(),
            }, is_best, trial.number, checkpoint=args.checkpoint)

        trial.report(test_acc, epoch)
        if trial.should_prune():
            raise optuna.exceptions.TrialPruned()

        print('Test_accuracy %.7f' % (test_acc))

    logger.close()
    logger.plot()
    savefig(os.path.join(args.checkpoint, 'log.eps'))

    print('Best acc:')
    print(best_acc)

    return best_acc


def train(train_loader, model, criterion, hm_criterion1, hm_criterion2, cam_transform, optimizer, epoch, use_cuda):
    # switch to train mode
    model.train()


    target_layers = [model.features4[-1], model.features3[-1], model.features2[-1], model.features[-1]]     # y6

    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    surg_ppe_top1 = AverageMeter()
    surg_ppe_top5 = AverageMeter()
    end = time.time()

    for batch_idx, (inputs, surg_ppe_targets) in enumerate(train_loader):
        # measure data loading time
        data_time.update(time.time() - end)

        if use_cuda:
            inputs = inputs.cuda(non_blocking=True)
            surg_ppe_targets = surg_ppe_targets.cuda(non_blocking=True)
            
        inputs, surg_ppe_targets = torch.autograd.Variable(inputs), torch.autograd.Variable(surg_ppe_targets)

        # compute output
        surg_ppe_outputs, outputs_hm1, outputs_hm2 = model(inputs)   # to be changed by including outputs_hm1, outputs_hm2

        surg_ppe_loss = criterion(surg_ppe_outputs, surg_ppe_targets)
        
        loss = (surg_ppe_loss)
        
        ############# class activation maps ###############################################
        with HiResCAM(model=model, target_layers=target_layers, use_cuda=use_cuda) as cam:
            cam.batch_size = 32
            grayscale_cam1 = cam(input_tensor=inputs, targets=None)
            grayscale_cam1 = np.expand_dims(grayscale_cam1, 1)
            grayscale_cam1 = torch.tensor(grayscale_cam1)
            grayscale_cam1 = transforms.Resize([128,256])(grayscale_cam1).cuda(non_blocking=True)
            grayscale_cam1 = torch.autograd.Variable(grayscale_cam1)
            
        loss_hires = hm_criterion1(outputs_hm1, grayscale_cam1)
        
        with XGradCAM(model=model, target_layers=target_layers, use_cuda=use_cuda) as cam:
            cam.batch_size = 32
            grayscale_cam2 = cam(input_tensor=inputs, targets=None)
            grayscale_cam2 = np.expand_dims(grayscale_cam2, 1)
            grayscale_cam2 = torch.tensor(grayscale_cam2)
            grayscale_cam2 = transforms.Resize([128,256])(grayscale_cam2).cuda(non_blocking=True)
            grayscale_cam2 = torch.autograd.Variable(grayscale_cam2)
            

        loss_fullgrad = hm_criterion2(outputs_hm2, grayscale_cam2)

        
        loss= loss + 4*loss_hires + 4*loss_fullgrad

        # measure accuracy and record loss
        surg_ppe_prec1, surg_ppe_prec1_dum = accuracy(surg_ppe_outputs.data, surg_ppe_targets.data, topk=(1, 1))
        surg_ppe_top1.update(surg_ppe_prec1.item(), inputs.size(0))
        
        losses.update(loss.item(), inputs.size(0))

        # compute gradient and do SGD step
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        batch_time.update(time.time() - end)
        end = time.time()

    train_accuracy = (surg_ppe_top1.avg)
    return (losses.avg, train_accuracy, surg_ppe_top1.avg)

def test(val_loader, model, criterion, epoch, use_cuda):
    global best_acc

    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    surg_ppe_top1 = AverageMeter()
    surg_ppe_top5 = AverageMeter()

    # switch to evaluate mode
    model.eval()

    end = time.time()
    bar = Bar('Processing', max=len(val_loader))
    for batch_idx, (inputs, surg_ppe_targets ) in enumerate(val_loader):
        # measure data loading time
        data_time.update(time.time() - end)

        if use_cuda:
            inputs, surg_ppe_targets = inputs.cuda(non_blocking=True), surg_ppe_targets.cuda(non_blocking=True)
        with torch.no_grad():
            inputs, surg_ppe_targets = torch.autograd.Variable(inputs), torch.autograd.Variable(surg_ppe_targets)

        # compute output
        surg_ppe_outputs, outputs_hm1, outputs_hm2 = model(inputs)

        surg_ppe_loss = criterion(surg_ppe_outputs, surg_ppe_targets)

        loss = (surg_ppe_loss)

        # measure accuracy and record loss
        surg_ppe_prec1, surg_ppe_prec1_dum = accuracy(surg_ppe_outputs.data, surg_ppe_targets.data, topk=(1, 1))

        surg_ppe_top1.update(surg_ppe_prec1.item(), inputs.size(0))
        
        losses.update(loss.item(), inputs.size(0))

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()

        # plot progress
        bar.suffix  = '({batch}/{size})Data:{data:.3f}s|Batch:{bt:.3f}s|Total:{total:}|ETA:{eta:}|Loss:{losses:.4f}|top1:{surg_ppe_top1: .4f}|'.format(
                    batch=batch_idx + 1,
                    size=len(val_loader),
                    data=data_time.avg,
                    bt=batch_time.avg,
                    total=bar.elapsed_td,
                    eta=bar.eta_td,
                    losses=losses.avg,
                    surg_ppe_top1=surg_ppe_top1.avg,
                    )
        bar.next()
    bar.finish()
    test_accuracy = (surg_ppe_top1.avg)
    return (losses.avg, test_accuracy, surg_ppe_top1.avg)

def save_checkpoint(state, is_best, trial_number, checkpoint='checkpoint', filename='checkpoint.pth.tar'):
    filepath = os.path.join(checkpoint, filename)
    torch.save(state, filepath)
    if is_best:
        shutil.copyfile(filepath, os.path.join(checkpoint, 'model_best_trial_'+str(trial_number)+'_epoch_'+str(state['epoch'])+'.pth.tar'))

def adjust_learning_rate(optimizer, epoch):
    global state
    if epoch in args.schedule:
        state['lr'] *= args.gamma
        for param_group in optimizer.param_groups:
            param_group['lr'] = state['lr']

if __name__ == '__main__':
    main()
