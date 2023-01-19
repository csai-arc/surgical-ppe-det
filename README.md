# CAM Based Fine-grained Spatial Feature Supervision On Surgical-PPE: A New Dataset For Surgical PPE Kit Presence Detection

This repository implements supervised contrastive loss in combination with cross entropy loss for surgical PPE kit presence detection for stage-1 training, HiResCAM and XGrad-CAM feature based supervision for surgical PPE kit presence detection for stage-2 training.

### Train:

This package needs an input txt file with the data list for training and testing. To initiate the stage-1 training, please use the below command.

 > python surgical_ppe_training_scmcl_stage1.py -a effnetv2_s --epochs 300 --data <'path to dataset> --gpu-id 0 -c <'path where checkpoints to be saved> --train-batch 25 --test-batch 2 --optuna_study_db sqlite:///./<'path where optuna db to be saved>
 
 
 To initiate stage-2 training, please use the below command.
 

 > python surgical_ppe_training_cam_stage2.py -a effnetv2_s --epochs 300 --data <'path to dataset> --gpu-id 0 -c <'path where checkpoints to be saved> --train-batch 22 --test-batch 2 --weights_load <'path to the best model saved from stage-2>  --optuna_study_db sqlite:///.<'path where optuna db to be saved>
 
 
### Architecture Overview:

The detailed network architecture information is given below:

Stage-1 training architecture overview
<img src="/images/table1.png?" width="70%" >

Stage-2 training architecture overview
<img src="/images/table2.png?" width="70%" >

Bottleneck block architecture overview
<img src="/images/table3.png?" width="70%" >

### Simple Inference Overview

Inference Overview is given in the below figure:
<img src="/images/simple_block.jpg?" width="70%" >

### Results:

Confusion Matrix for the proposed methodology is given below:

<img src="/images/confusion_matrix.jpg?" width="50%" >


For trained network models please contact the author.

### "Surgical-PPE": A New Dataset For Surgical PPE Kit Presence Detection

Sample Surgical PPE kits:

<img src="/images/ppe_vs_nonppe.jpg?" width="50%" >

Surgeons attires (a) Surgical PPE kits are usually loosely fitted around the joints of the personnel, (b) Surgeon not wearing a PPE kit

Sample "Surgical PPE" dataset annotations:

<img src="/images/sample_surgical_ppe_labels.png?" width="90%" >

Class label "0" denotes Non-PPE and Class label "1" denotes PPE

Dataset link: Coming Soon
