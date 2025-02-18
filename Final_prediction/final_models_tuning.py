import torch
from torch.utils.data import DataLoader, Dataset
import torch.nn as nn
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_curve, auc, precision_recall_curve, ConfusionMatrixDisplay
import matplotlib.pyplot as plt

datatsets_dir = 'D:\\year 4\\semester 1\\BT\\BT 4033\\prediction\\'
output_dir = 'D:\\year 4\\semester 1\\BT\\BT 4033\\prediction\\'


class ProteinDataset(Dataset):
    def __init__(self, input_data, output_data):
        """
        Args:
            input_data (numpy.ndarray): Input features, shape (num_samples, num_features)
            output_data (numpy.ndarray): Targets, shape (num_samples, )
        """
        self.input_data = input_data
        self.output_data = output_data
    
    def __len__(self):
        return len(self.input_data)
    
    def __getitem__(self, idx):
        # Return a single sample as a tuple
        return self.input_data[idx], self.output_data[idx]


def loadData(aspect):   #aspects = ['bp', 'cc', 'mf']
    train_data = torch.load(f'{datatsets_dir}train_dataset_{aspect}.pt')
    val_data = torch.load(f'{datatsets_dir}val_dataset_{aspect}.pt')
    test_data = torch.load(f'{datatsets_dir}test_dataset_{aspect}.pt')
    return train_data, val_data, test_data


def calc_class_weights(true_labels):
    true_labels = true_labels.numpy()
    train_class_counts = np.sum(true_labels == 1, axis=0)
    class_weights = class_weights = true_labels.shape[0]/(train_class_counts)
    return torch.from_numpy(class_weights)


def standadize_inputs(train, val, test):
    scaler = StandardScaler()
    train_std = scaler.fit_transform(train.numpy())
    val_std = scaler.transform(val.numpy())
    test_std = scaler.transform(test.numpy())
    train_std, val_std, test_std = torch.from_numpy(train_std).float(), torch.from_numpy(val_std).float(), torch.from_numpy(test_std).float()
    return train_std, val_std, test_std


def calculate_accuracy(predictions, labels, threshold=0.5):
    
    predicted_labels = (predictions > threshold).astype(int)
   
    num_classes = labels.shape[1]
    TP, FP, TN, FN = 0, 0, 0, 0

    for class_idx in range(num_classes):
        y_true = labels[:, class_idx]
        y_pred = predicted_labels[:, class_idx]
        
        # Calculate TP, TN, FP, FN
        tp = np.sum((y_true == 1) & (y_pred == 1), axis=0)
        tn = np.sum((y_true == 0) & (y_pred == 0), axis=0)
        fp = np.sum((y_true == 0) & (y_pred == 1), axis=0)
        fn = np.sum((y_true == 1) & (y_pred == 0), axis=0)
        
        TP += tp
        FP += fp
        TN += tn
        FN += fn
    accuracy = (TP+TN)/(TP+TN+FP+FN)
    return accuracy


def train_model(model, inputs, labels, criterion, optimizer):
    global train_accuracies, train_losses
    model.train()  
    optimizer.zero_grad()
    outputs = model(inputs)
    # loss = criterion(outputs, labels)
    loss = criterion(outputs.sigmoid(), labels)
    train_losses = train_losses + [loss.item()]
    loss.backward()
    optimizer.step()

    probabilities = outputs.sigmoid()  
    accuracy = calculate_accuracy(probabilities.detach().numpy(), labels.numpy())
    train_accuracies = train_accuracies + [accuracy]
    return loss.item(), accuracy 


def test_model(model, inputs, labels, criterion, validation = False):
    global test_accuracies, test_losses, val_accuracies, val_losses
    model.eval()  

    with torch.no_grad():  
        outputs = model(inputs)
        # loss = criterion(outputs, labels)
        loss = criterion(outputs.sigmoid(), labels)
        if validation:
            val_losses = val_losses + [loss.item()]
        else:
            test_losses = test_losses + [loss.item()]

    probabilities = outputs.sigmoid()
    accuracy = calculate_accuracy(probabilities.numpy(), labels.numpy())
    if validation:
        val_accuracies = val_accuracies + [accuracy]
    else:
        test_accuracies = test_accuracies + [accuracy]

    return loss.item(), accuracy


class EarlyStopping:
    def __init__(self, patience=5, delta=0, path='D:\\year 4\\semester 1\\BT\\BT 4033\\prediction\\best.pt'):
        """
        Args:
            patience (int): How many epochs to wait before stopping if no improvement.
            delta (float): Minimum change to qualify as improvement.
            path (str): Path to save the best model.
        """
        self.patience = patience
        self.delta = delta
        self.path = path
        self.best_val_acc = 0 
        self.epochs_no_improve = 0
        self.early_stop = False

    def __call__(self, val_acc, model):
        if val_acc > self.best_val_acc + self.delta:  # AUC should increase
            self.best_val_acc = val_acc
            self.epochs_no_improve = 0
            torch.save(model.state_dict(), self.path)  # Save best model
        else:
            self.epochs_no_improve += 1
            if self.epochs_no_improve >= self.patience:
                self.early_stop = True


class BP_PredictorModel(nn.Module):
    def __init__(self, input_size, output_size, num_layers):
        super(BP_PredictorModel, self).__init__()
        self.layers = nn.ModuleList()
        self.layers.append(nn.Linear(input_size, input_size))  
        
        for _ in range(num_layers):
            self.layers.append(nn.Linear(input_size, input_size))  
        
        self.output_layer = nn.Linear(input_size, output_size)

    def forward(self, x):
        for layer in self.layers:
            x = layer(x).relu()
        x = self.output_layer(x)
        return x



##########################################################################
for aspect in ['bp', 'mf', 'cc']:
    aspect_dict = {'bp':'Biological Process',
                   'mf': 'Molecular Function',
                   'cc': 'Cellular Component'}
    
    train_data, val_data, test_data = loadData(aspect)
    input_feature_len = train_data['input'].shape[1]
    output_vect_len = train_data['output'].shape[1]
    class_weights = calc_class_weights(train_data['output'])
    trainX_std, valX_std, testX_std = standadize_inputs(train_data['input'], val_data['input'], test_data['input'])
    dataset = ProteinDataset(trainX_std, train_data['output'])
    dataloader = DataLoader(dataset, batch_size=128, shuffle=True)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    # criterion = nn.BCEWithLogitsLoss(pos_weight=class_weights)


    pr_curves, roc_curves = [], []
    for alpha in [0.1, 0.01, 0.001]:
        for hid_layer in range(0, 3):
            early_stopping = EarlyStopping(patience=5, delta=0.001)
            model = BP_PredictorModel(input_feature_len, output_vect_len, hid_layer)
            best_model = None
            optimizer = torch.optim.Adam(model.parameters(), lr=alpha)
            print(f'when number of layers = {hid_layer+1} and alpha = {alpha}......')
            num_epochs = 100
            train_accuracies = []
            test_accuracies = []
            train_losses = []
            test_losses = []
            val_losses = []
            val_accuracies = []

            for epoch in range(num_epochs):
                for batch_inputs, batch_outputs in dataloader:
                    train_loss, train_accuracy = train_model(model, batch_inputs, batch_outputs.to(torch.float), criterion, optimizer)
                    test_loss, test_accuracy = test_model(model, testX_std, test_data['output'], criterion)
                    val_loss, val_accuracy = test_model(model, valX_std, val_data['output'], criterion, validation= True)

                print(f"Epoch {epoch}, "
                            f"Train Loss: {train_loss:.4f}, Train Acc: {train_accuracy:.4f}, "
                            f"Test Loss: {test_loss:.4f}, Test Acc: {test_accuracy:.4f}, " 
                            f"Val Loss: {val_loss:.4f}, Val Acc: {val_accuracy:.4f}")
                
                early_stopping(val_accuracy, model)
                if early_stopping.early_stop:
                    print("Early stopping triggered!")
                    break
                best_model = model

            #### metrics 
            true_labels = test_data['output'].numpy().astype(int)
            best_model.eval()
            with torch.no_grad():
                outputs = best_model(testX_std).sigmoid().numpy()
                predicted_labels = (outputs > 0.5).astype(int)

            y_true_flat = true_labels.ravel()
            y_pred_flat = outputs.ravel()

            fpr_all, tpr_all, _ = roc_curve(y_true_flat, y_pred_flat)
            roc_auc_all = auc(fpr_all, tpr_all)

            roc_curves.append([fpr_all, tpr_all, roc_auc_all ,hid_layer, alpha])

            precision_all, recall_all, _ = precision_recall_curve(y_true_flat, y_pred_flat)
            pr_auc_all = auc(recall_all, precision_all)
            pr_curves.append([recall_all, precision_all, pr_auc_all, hid_layer, alpha])


    # Plot combined PR curve
    plt.figure()
    for pr in pr_curves:
        plt.plot(pr[0], pr[1],  lw=2, label=f'AUC = {pr[2]:.2f} no.dense layers {pr[3]+1} lr = {pr[4]}')
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title(f'Overall Precision-Recall Curve for Multi-label Classification - {aspect_dict[aspect]}')
    plt.legend(loc="lower left")
    plt.savefig(f'{output_dir}{aspect}_pr.png', dpi=300.0)

    # Plot combined ROC
    plt.figure()
    for roc in roc_curves:
        plt.plot(roc[0], roc[1], lw=2, label=f'AUC = {roc[2]:.2f} no.dense layers = {roc[3]+1} lr = {roc[4]}')
    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title(f'Overall ROC Curve for Multi-label classification - {aspect_dict[aspect]}')
    plt.legend(loc="lower right")
    plt.savefig(f'{output_dir}{aspect}_roc.png', dpi=300.0)

