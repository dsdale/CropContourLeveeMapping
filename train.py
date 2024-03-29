import itertools
import json
import os
import random as rn
import shutil
import statistics
import sys
import time
from base64 import *
from glob import glob
from shutil import copyfile

import cv2
import imgaug.augmenters as iaa
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import tensorflow as tf
import tensorflow.keras as tk
import tensorflow.keras.backend as K
from PIL import Image, ImageColor, ImageDraw
from matplotlib import cm
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from osgeo import gdal, ogr
from sklearn.metrics import auc, confusion_matrix, f1_score, jaccard_score, precision_score, recall_score, roc_auc_score, roc_curve

#These are the paths that needs changed
path_label = "/Users/dakota/Desktop/LonokeComplete"#Path to unprocessed LIF files
path_55 = "/Users/dakota/Desktop/55tilesComplete"#Path to the "55 Tiles". Contains both image and label as separate .tif

#Intermediary directories
path_processed = 'data'
path_processed_save = 'keep'

if not os.path.isdir(path_processed):
    os.mkdir(path_processed)
if not os.path.isdir(os.path.join(path_processed, 'img')):
    os.mkdir(os.path.join(path_processed, 'img'))
if not os.path.isdir(os.path.join(path_processed, 'label')):
    os.mkdir(os.path.join(path_processed, 'label'))

if not os.path.isdir(path_processed_save):
    os.mkdir(path_processed_save)
if not os.path.isdir(os.path.join(path_processed_save, 'X')):
    os.mkdir(os.path.join(path_processed_save, 'X'))
if not os.path.isdir(os.path.join(path_processed_save, 'Y')):
    os.mkdir(os.path.join(path_processed_save, 'Y'))
if not os.path.isdir(os.path.join(path_processed_save, 'X','train')):
    os.mkdir(os.path.join(path_processed_save, 'X','train'))
if not os.path.isdir(os.path.join(path_processed_save, 'X','val')):
    os.mkdir(os.path.join(path_processed_save, 'X','val'))
if not os.path.isdir(os.path.join(path_processed_save, 'X','test')):
    os.mkdir(os.path.join(path_processed_save, 'X','test'))
if not os.path.isdir(os.path.join(path_processed_save, 'Y','train')):
    os.mkdir(os.path.join(path_processed_save, 'Y','train')) 
if not os.path.isdir(os.path.join(path_processed_save, 'Y','val')):
    os.mkdir(os.path.join(path_processed_save ,'Y','val'))
if not os.path.isdir(os.path.join(path_processed_save, 'Y','test')):
    os.mkdir(os.path.join(path_processed_save, 'Y','test'))  
if not os.path.isdir(os.path.join(path_processed_save, 'Y','pred')):
    os.mkdir(os.path.join(path_processed_save, 'Y','pred'))  





"""## Conversion"""



def compose_file_list(dir_img, dir_mask,suffix='.tif'):
    imgs = []
    for imgName in glob.glob(dir_img +'*'+suffix):
        imgs.append(imgName)
    imgs.sort()

    masks = []
    for maskName in glob.glob(dir_mask +'*' +suffix):
        masks.append(maskName)
    masks.sort()

    filename_pairs = []
    if len(masks) == len(imgs) and len(imgs) > 0:
        for i in range(len(masks)):
            # print(masks[i])
            filename_pairs.append((imgs[i], masks[i]))
    return filename_pairs


def read_batch_imgs(dataList,width,height):

    img_array = np.ndarray((len(dataList),width, height, 3), np.uint8)
    mask_array = np.ndarray((len(dataList), width, height, 1), np.uint8)
    n_img = 0

    for fimg,fmask in dataList:
        img_array[n_img,:,:,:] = np.array(Image.open(fimg))
        mask_array[n_img, :, :,0] = np.array(Image.open(fmask))
        n_img = n_img +1

    return img_array,mask_array


def adjustData(img,mask,flag_multi_class,num_class):
    if(flag_multi_class):
        img = img / 255
        mask = mask[:,:,:,0] if(len(mask.shape) == 4) else mask[:,:,0]
        new_mask = np.zeros(mask.shape + (num_class,))
        for i in range(num_class):
            #for one pixel in the image, find the class in mask and convert it into one-hot vector
            #index = np.where(mask == i)
            #index_mask = (index[0],index[1],index[2],np.zeros(len(index[0]),dtype = np.int64) + i
            #) if (len(mask.shape) == 4) else (index[0],index[1],np.zeros(len(index[0]),dtype = np.int64) + i)
            #new_mask[index_mask] = 1
            new_mask[mask == i,i] = 1
        new_mask = np.reshape(
            new_mask,
            (new_mask.shape[0],new_mask.shape[1]*new_mask.shape[2],new_mask.shape[3])
        ) if flag_multi_class else np.reshape(
            new_mask,
            (new_mask.shape[0]*new_mask.shape[1],new_mask.shape[2])
        )
        mask = new_mask
    elif(np.max(img) > 1):
        img = img / 255
        mask = mask /255
        mask[mask > 0.5] = 1
        mask[mask <= 0.5] = 0
    return (img,mask)

GenerateSpecificMask = True

SpecificMask = 2

numContour = 0
numStraight = 0
numPivot = 0
numZero = 0
numUnknown = 0

dict_color = {
    'u': 'white',
    'c': 'red',
    's': 'green',
    'p': 'blue',
    'z': 'yellow',
}
dict_code = {
    'u': 1,
    'c': 2,
    's': 3,
    'p': 4,
    'z': 5,
}

def _decode_lif_file(srcLIFfile):
    '''
    :param srcLIFfile: input lif file
    :return imageData: the image part in lif file
    :return shapes: poygons in lif file
    '''
    with open(srcLIFfile,"rb") as f:
        data = json.load(f)
        imagePath = data['imagePath']
        imageData = b64decode(data['imageData'])
        shapes = ((s['label'],s['points'],s['line_color'],s['fill_color'])\
                  for s in data['shapes'])
    return imageData,shapes

def PolyArea(x,y):
  return 0.5*np.abs(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1)))
areaOfPolygons = []
def imgs_masks_from_lif(srcLIFfile,dstImg=None,
                        dstMask=None,dstShapes=None):
    '''
    :param srcLIFfile: input Lif file
    :param dstImg: output tiff image
    :param dstMask: output mask
    :param dstShapes: output shapefile of the mask
    :return:
    '''
    global numContour 
    global numStraight 
    global numPivot
    global numZero 
    global numUnknown
    global areaOfPolygons
    
    try:
        imageData, shapes = _decode_lif_file(srcLIFfile)
    except Exception as e:
      raise(e)

    if dstImg != None:
        try:
            outImg = open(dstImg,'wb')
            outImg.write(imageData)
            outImg.close()
        except Exception as e:
            raise(e)

        try:
            src_ds = gdal.Open((dstImg))
        except RuntimeError as e:
            print('Unable to open %s',dstImg)
            print(e)
            sys.exit(1)

        cols = src_ds.RasterXSize
        rows = src_ds.RasterYSize

        im = Image.open(dstImg)
        shape_Img = im.size

        n_x = shape_Img[0]
        n_y = shape_Img[1]
        array = np.zeros((n_x, n_y), dtype=np.uint8)
        img_mask = Image.fromarray(array, mode='L')
        if GenerateSpecificMask:
          img_mask_spec = Image.fromarray(array, mode='L')
          draw_spec = ImageDraw.Draw(img_mask_spec)
        draw = ImageDraw.Draw(img_mask)
        
        dstMask = dstMask[:-4]
        
        
        polygonCoordinates = []
       
        for ploygon in shapes:
            #print(ploygon[0])
            Coordinates = ploygon[1]
            polygonCoordinates.append(Coordinates)
            xy_list = []
            for xy_pair in Coordinates:
                xy_list.append(xy_pair[0])
                xy_list.append(xy_pair[1])

            xy_list = tuple(xy_list)

            # color = dict_color[ploygon[0]]
            # draw.polygon(xy_list, color, color)
            code = dict_code[ploygon[0]]
            #print(code)
            if code == 1:
                numUnknown+=1
            if code == 2:
              numContour+=1
            if code == 3:
              numStraight+=1
            if code == 4:
              numPivot+=1
            if code == 5:
              numZero+=1
            if GenerateSpecificMask and code == SpecificMask:
              areaOfPolygons.append(PolyArea([x[0] for x in Coordinates], [y[1] for y in Coordinates]))
              draw_spec.polygon(xy_list, code, code)
            else:
              draw.polygon(xy_list, code, code)

        if dstMask!=None:
          if GenerateSpecificMask:
            img_mask_spec.save(dstMask + '.tif')
          else:
            img_mask.save(dstMask + '.tif')

        if dstShapes != None:
            driver = ogr.GetDriverByName("ESRI Shapefile")
            ds_new = driver.CreateDataSource(dstShapes)
            layernew = ds_new.CreateLayer('Samples', None, ogr.wkbPolygon)

            for ploygon in polygonCoordinates:
                ring = ogr.Geometry(ogr.wkbLinearRing)
                first_p = ploygon[0]
                for xy_pair in ploygon:
                    ring.AddPoint(xy_pair[0],xy_pair[1])
                ring.AddPoint(first_p[0],first_p[1])
                poly = ogr.Geometry(ogr.wkbPolygon)
                poly.AddGeometry(ring)
                feat = ogr.Feature(layernew.GetLayerDefn())
                feat.SetGeometry(poly)
                layernew.CreateFeature(feat)
            ds_new.Destroy()

        print("Average polygon area: ", sum(areaOfPolygons)/len(areaOfPolygons))
        print("Stdev polygon area: ",statistics.stdev(areaOfPolygons))
        print("Max Polygon area: ", max(areaOfPolygons))
        print("Min Polygon area: ", min(areaOfPolygons))
        return imageData,img_mask,shapes


arr_color = [(0, 0, 0)]
for k in dict_color:
    arr_color.append(ImageColor.getrgb(dict_color[k]))
arr_color = np.array(arr_color)

[k for k in dict_color]
Grayscale = True #@param {type:"boolean"}

def gray(filename):

    img = Image.open(filename)

    img.getdata()
    #print(img.split())
    tup = img.split()
    if len(tup) == 3:
      r, g, b = tup
    else:
      return

    ra = np.array(r)
    ga = np.array(g)
    ba = np.array(b)

    gray = (0.299*ra + 0.587*ga + 0.114*ba)

    img = Image.fromarray(gray)
    img.save(filename)

#generateMask.py



def _array_to_raster(array,dst_filename,x_size,y_size,x_pixels,y_pixels,x_min,y_max,wkt_projection,datatype):
    """Array > Raster
    Save a raster from a C order array.

    :param array: ndarray
    :dst_filename: filename
   """

    geotransform = (x_min, x_pixels, 0, y_max, 0, y_pixels)
    dims = min(array.shape)


    if len(array.shape) == 2:
        n_bands = 1
    if len(array.shape) > 2 and dims >0 and dims < 32:
        n_bands = 3


    # create the n-band raster file
    dst_ds = gdal.GetDriverByName('GTiff').Create(dst_filename, x_size, y_size, n_bands, datatype)

    dst_ds.SetGeoTransform(geotransform)  # specify coords
    dst_ds.SetProjection(wkt_projection)  # export coords to file
    if n_bands > 1:
        for i in range(n_bands):
            dst_ds.GetRasterBand(i+1).WriteArray(array[i,:,:])  # write a band to the raster
    if n_bands == 1:
        dst_ds.GetRasterBand(1).WriteArray(array)

    dst_ds.FlushCache()  # write to disk
    dst_ds = None
    return True


def spatial_subset_image(srcImgfile,outsize,dstPath,startX=0,startY=0,sBand=0):
    '''Get spatial subset of a image by
    a moving window.

    :param infile: image file in geotiff format.
    :param outpath: image file in geotiff format.
    :param size: subset size of image
    :return: true if it sucess, otherwise false
    '''
    try:
        src_ds = gdal.Open(srcImgfile)
    except RuntimeError as e:
        print("Unable to open %s",srcImgfile)
        return False
    cols = src_ds.RasterXSize
    rows = src_ds.RasterYSize
    proj_ds = src_ds.GetProjectionRef()
    trans_ds = src_ds.GetGeoTransform()
    datatype = src_ds.GetRasterBand(1).DataType

    if outsize > cols or outsize > rows:
        print("The  size of output image is larger than the inpot image.")
        print(outsize)
        print(cols)
        print(rows)
        return False

    n_img_cols = int((cols - cols%outsize)/outsize)
    n_img_rows = int((rows - rows%outsize)/outsize)
    cols_begin = int((cols%outsize)/2)
    rows_begin = int((rows%outsize)/2)

    img = np.array(src_ds.ReadAsArray())
    n_dims = len(img.shape)

    for i_col in range(n_img_cols):
        cols_head = cols_begin + i_col*outsize
        for i_row in range(n_img_rows):
            row_head = rows_begin + i_row*outsize
            dst_name = dstPath +"_"+str(i_col) + "_" + str(i_row) +".tif"
            x_min = trans_ds[0] + trans_ds[1]*cols_head
            y_max =  trans_ds[3] +  trans_ds[5]*row_head
            if n_dims > 2 and sBand ==0:
                out_array = img[0:3,row_head:(row_head+outsize),cols_head:(cols_head+outsize)]

                _array_to_raster(img[:,row_head:(row_head+outsize),cols_head:(cols_head+outsize)], 
                                 dst_name, outsize, outsize, trans_ds[1], trans_ds[5], 
                                 x_min, y_max, proj_ds,datatype)
            elif n_dims > 2 and sBand ==1:
                out_array = img[0,row_head:(row_head+outsize),cols_head:(cols_head+outsize)]

                _array_to_raster(
                    img[0,row_head:(row_head+outsize),cols_head:(cols_head+outsize)], 
                    dst_name, outsize, outsize, trans_ds[1], trans_ds[5], 
                    x_min, y_max, proj_ds,datatype
                )
            else:
                _array_to_raster(
                    img[row_head:(row_head+outsize),cols_head:(cols_head+outsize)], 
                    dst_name, outsize, outsize, trans_ds[1], trans_ds[5], 
                    x_min, y_max, proj_ds,datatype
                )

    src_ds = None
    return True

if __name__ == "__main__":
    lifImgPath = path_label
    trainImgPath = path_processed
    
    outsize = 960
    names = os.listdir(lifImgPath)
    for fnameAll in names[:16]:
        fname0 = os.path.splitext(os.path.split(fnameAll)[-1])[0]
        inLif = os.path.join(lifImgPath, fname0 + ".lif")
        print(inLif)
        outImg = os.path.join(trainImgPath, fname0 + ".tif")
        outMask = os.path.join(trainImgPath, fname0 + "_Mask.tif")
        imgs_masks_from_lif(
            inLif,
            dstImg=outImg,
            dstMask=outMask
        )

        if Grayscale:
          gray(outImg)

        spatial_subset_image(
            outImg, outsize, 
            os.path.join(trainImgPath, 'img', fname0)
        )
        spatial_subset_image(
            outMask, outsize, 
            os.path.join(trainImgPath, 'label', fname0 + "_Mask"),
            sBand=1
        )

print("Number of Unknown: ",numUnknown)
print("Number of Contour: ",numContour)
print("Number of Straight: ",numStraight)
print("Number of Pivot: ",numPivot)
print("Number of Zero: ",numZero)
numContour = 0
numStraight = 0
numPrivot = 0
numZero = 0
numUnknown = 0

f_base = 'Lonoke102'
f_sub = '1_4'

f_img = f'{path_processed}/{f_base}.tif'
f_label = f'{path_processed}/{f_base}_Mask.tif'

data_img = plt.imread(f_img) / 255
data_label = arr_color[plt.imread(f_label)]
fig, ax = plt.subplots(1, 2, figsize=(24, 12))
ax[0].imshow(data_img)
ax[1].imshow(data_label);

for ratio_shrink in [2, 3, 4, 8]:
    fig, ax = plt.subplots(1, 2, figsize=(24, 12))
    ax[0].imshow(data_img[::ratio_shrink, ::ratio_shrink])
    ax[1].imshow(data_label[::ratio_shrink, ::ratio_shrink])
    ##plt.show()

"""# Classification"""

# Run it to obtain reproducible results across machines (from  keras.io)

os.environ['PYTHONHASHSEED'] ='0'

#np.random.seed(42)
np.random.seed(5)

rn.seed(12345)

# load data func

MEAN_B = 103.939 
MEAN_G = 116.779
MEAN_R = 123.68

def getData(dataset_dir, limit=None, b_shuffle=True, idx=None, ratio_shrink=1, code_y=2, test=False):
    '''
    ratio_shrink: int
    '''    
    
    X_list = np.array(sorted(glob(os.path.join(dataset_dir, 'img', '*.tif'))))
    print("number of x:", len(X_list))
    Y_list = np.array(sorted(glob(os.path.join(dataset_dir, 'label', '*.tif'))))
    
    # Shuffle the training data

    if idx is None:
        idx =list(range(X_list.shape[0]))
    if b_shuffle:
        np.random.shuffle(idx)
    
    if limit is None:
        limit = len(X_list)
    X_list = X_list[idx[:limit]]
    Y_list = Y_list[idx[:limit]]

    X= []

    Y= []

    for i in range(len(X_list)):

        # Load input image

        x =  tk.preprocessing.image.load_img(X_list[i])

        x =  tk.preprocessing.image.img_to_array(x)
        
        if ratio_shrink > 1:
            x = x[::ratio_shrink, ::ratio_shrink]
            
        # Convert to ImageNet (Caffe) style
        x = x[:, :, ::-1]
        x[:, :, 0] -= MEAN_B
        x[:, :, 1] -= MEAN_G
        x[:, :, 2] -= MEAN_R

        X.append(x)

        # Load ground-truth label and encode it to label 0  and 1
        if test:
          x = Image.open(Y_list[i])
          x = np.asarray(x)
        else:
          x =  tk.preprocessing.image.load_img(Y_list[i])

          x =  tk.preprocessing.image.img_to_array(x)[:, :, [0]]
        
        if ratio_shrink > 1:
            x = x[::ratio_shrink, ::ratio_shrink]

        
        x = (x == code_y).astype('float')

        Y.append(x)

    X = np.asarray(X)

    Y = np.asarray(Y)
    Y = np.reshape(Y, (Y.shape[0],Y.shape[1],Y.shape[2],1))

    return X, Y

def inverse_convert(img_caffe):
    img_res = img_caffe.copy()
    img_res[:, :, 0] += MEAN_B
    img_res[:, :, 1] += MEAN_G
    img_res[:, :, 2] += MEAN_R
    img_res = img_res[:, :, ::-1]
    return img_res/255.0

ratio_shrink = 3
width = outsize // ratio_shrink
outsize, width

Reshuffle = False
Seed = 20
if Reshuffle:
  np.random.seed(Seed)

# load data
dataset_path = 'data'

X, Y = getData('data', b_shuffle= True, ratio_shrink=3)

print(X.shape,' ', Y.shape)

X.min(), X.max(), Y.min(), Y.max()

def createDir(path,Input,masks=True,fromLIF = True):
    if not os.path.isdir(path):
      os.mkdir(path)
    if not os.path.isdir(os.path.join(path, 'img')):
        os.mkdir(os.path.join(path, 'img'))
    if not os.path.isdir(os.path.join(path, 'label')) and masks:
        os.mkdir(os.path.join(path, 'label'))

    lifImgPath = Input

    trainImgPath = path

    outsize = 960
    if fromLIF:
      names = os.listdir(lifImgPath)
    else:
      names = glob(Input+"/*_Mask.tif")
    print(names)
    for fnameAll in names:
        fname0 = os.path.splitext(os.path.split(fnameAll)[-1])[0]
        if fromLIF:
          outImg = os.path.join(trainImgPath, fname0 + ".tif")
        else:
          outImg = os.path.join(trainImgPath, fname0[:-5] + ".tif")
        print(outImg)
        if masks:
          if fromLIF:
            inLif = os.path.join(lifImgPath, fname0 + ".lif")
            #print(inLif)
            outMask = os.path.join(trainImgPath, fname0 + "_Mask.tif")
            imgs_masks_from_lif(
                inLif,
                dstImg=outImg,
                dstMask=outMask
            )
          else:
             outMask = os.path.join(trainImgPath, fname0+".tif")
             print(outMask)
             print(outImg)
             shutil.copy(fnameAll, outMask)
             shutil.copy(os.path.join(Input, fname0[:-5] + ".tif"), outImg)
          if Grayscale:
            print("Graying..",outImg)
            gray(outImg)
          spatial_subset_image(
              outMask, outsize, 
              os.path.join(trainImgPath, 'label', fname0 + "_Mask"),
              sBand=1
          )
        spatial_subset_image(
            outImg, outsize, 
            os.path.join(trainImgPath, 'img', fname0)
        )


numContour = 0
numStraight = 0
numPivot = 0
numZero = 0
numUnknown = 0
createDir('data',path_label)



numContour = 0
numStraight = 0
numPivot = 0
numZero = 0
numUnknown = 0

print("Number of Unknown: ",numUnknown)
print("Number of Contour: ",numContour)
print("Number of Straight: ",numStraight)
print("Number of Pivot: ",numPivot)
print("Number of Zero: ",numZero)

AdjustTrain = True
j = 4 

if AdjustTrain:
  idx_train = slice(X.shape[0] * j // 10)
  idx_val = slice(X.shape[0] * j // 10, X.shape[0] * int((((10-j)/2)+j)) // 10)
  idx_test = slice(X.shape[0] * int((((10-j)/2)+j)) // 10, X.shape[0])
else:
  idx_train = slice(X.shape[0] * 3 // 5)
  idx_val   = slice(X.shape[0] * 3 // 5, X.shape[0] * 4 // 5)
  idx_test  = slice(X.shape[0] * 4 // 5, X.shape[0])

X_train, Y_train = X[idx_train], Y[idx_train]
X_val, Y_val = X[idx_val], Y[idx_val]
X_test, Y_test = X[idx_test], Y[idx_test]
X_train.shape, Y_train.shape, X_val.shape, Y_val.shape, X_test.shape, Y_test.shape



"""## ResNet"""


def get_resunet(resnet=None, b_retrain=True):
    if resnet is None:
        net_input = tk.layers.Input(shape=(width, width, 3))
        resnet = tk.applications.resnet50.ResNet50(include_top=False, weights='imagenet', input_tensor=net_input)
        
    for layer in resnet.layers[:-1]:
        layer.trainable = b_retrain

    encode1 = resnet.layers[0].output # original size, 3 channels
    encode2 = resnet.layers[4].output # 1/2 size, 64 channels
    encode3 = resnet.layers[38].output # 1/4 size, 256 channels
    encode4 = resnet.layers[80].output # 1/8 size, 512 channels
    encode5 = resnet.layers[142].output # 1/16 size, 1024 channels
    encode6 = resnet.layers[174].output # 1/32 size, 2048 channels

    decode5 = tk.layers.Conv2DTranspose(
        512, (3,3), strides=(2,2), activation = 'relu', padding = 'same', 
        kernel_initializer = 'he_normal', name='decode5',
    )(encode6)
    merge5 = tk.layers.concatenate([encode5, decode5], axis = 3, name='merge5')
    decode4 = tk.layers.Conv2DTranspose(
        512, (3,3), strides=(2,2), activation = 'relu', padding = 'same', 
        kernel_initializer = 'he_normal', name='decode4',
    )(merge5)
    merge4 = tk.layers.concatenate([encode4, decode4], axis = 3, name='merge4')
    decode3 = tk.layers.Conv2DTranspose(
        256, (3,3), strides=(2,2), activation = 'relu', padding = 'same', 
        kernel_initializer = 'he_normal', name='decode3',
    )(merge4)
    merge3 = tk.layers.concatenate([encode3, decode3], axis = 3, name='merge3')
    decode2 = tk.layers.Conv2DTranspose(
        64, (3,3), strides=(2,2), activation = 'relu', padding = 'same', 
        kernel_initializer = 'he_normal', name='decode2',
    )(merge3)
    merge2 = tk.layers.concatenate([encode2, decode2], axis = 3, name='merge2')
    decode1 = tk.layers.Conv2DTranspose(
        8, (3,3), strides=(2,2), activation = 'relu', padding = 'same', 
        kernel_initializer = 'he_normal', name='decode1',
    )(merge2)
    merge1 = tk.layers.concatenate([encode1, decode1], axis = 3, name='merge1')

    sigmoid = tk.layers.Conv2D(
        1, 3, activation = 'sigmoid', padding = 'same', kernel_initializer = 'he_normal', name='sigmoid',
    )(merge1)

    model = tk.models.Model(inputs=resnet.input, outputs=sigmoid)

    return model

name_model = 'resunet'

model = get_resunet()

early = tk.callbacks.EarlyStopping(monitor='val_loss', min_delta=1e-4, patience=10)
save = tk.callbacks.ModelCheckpoint('%s.h5'%name_model, save_best_only=True)
reduce = tk.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.1, patience=5)

loss=tk.losses.binary_crossentropy
optimizer=tk.optimizers.RMSprop(lr=5e-4)

def removeFromList(list,elements):
  for i in elements:
    list.remove(i)

b_tpu = False 

def jaccard_distance_loss(y_true, y_pred, smooth=100):
    """
    Jaccard = (|X & Y|)/ (|X|+ |Y| - |X & Y|)
            = sum(|A*B|)/(sum(|A|)+sum(|B|)-sum(|A*B|))
    
    The jaccard distance loss is usefull for unbalanced datasets. This has been
    shifted so it converges on 0 and is smoothed to avoid exploding or disapearing
    gradient.
    
    Ref: https://en.wikipedia.org/wiki/Jaccard_index
    
    @url: https://gist.github.com/wassname/f1452b748efcbeb4cb9b1d059dce6f96
    @author: wassname
    """

    intersection = K.sum(K.abs(y_true * y_pred), axis=-1)
    sum_ = K.sum(K.abs(y_true) + K.abs(y_pred), axis=-1)
    jac = (intersection + smooth) / (sum_ - intersection + smooth)
    return (1 - jac) * smooth

def hybrid_loss(y_true, y_pred):
    loss = tk.losses.binary_crossentropy(y_true, y_pred) + jaccard_distance_loss(y_true, y_pred)
    return loss


def loadToDirectory(array, dir, test=False):
  if array.shape[3] == 1:
    compDir = 'data/label/'
    outShp = (320,320,1)
    _ , im= getData(dataset_path, b_shuffle= False, ratio_shrink=3)
  else:
    compDir = 'data/img/'
    outShp = (320,320,3)
    im, _ = getData(dataset_path, b_shuffle= False, ratio_shrink=3)
  fileList = glob(compDir + "*.tif")
  fileList.sort()
  found =[]
  for i in range(array.shape[0]):
    for x, f in enumerate(fileList):
      tif = im[x]
      arr = array[i,:,:,:]
      if np.array_equal(tif,arr):
        print("Found match", "os.path.split(f)", "Copying...",os.path.join(dir,os.path.split(f)[1]))
        if test:
          predictionsList.append(f)
        if array.shape[3] == 3:
          if os.path.split(f)[1] in found:
            break
          try:
            copyfile(f, os.path.join(dir,os.path.split(f)[1]))
            found.append(os.path.split(f)[1])
          except Exception as e:
            continue
        else:
          print("Copying label...")
          print(f)
          fileName = os.path.basename(f)
          fileName = fileName.replace("_Mask","")
          if "test" in dir:
            path = "keep/X/test/" + fileName
          if "train" in dir:
            path = "keep/X/train/" + fileName
          if "val" in dir:
            path = "keep/X/val/" + fileName
          if not os.path.exists(path):
            print("Path doesnt exist")
            break
          print("Opening corresponding image...")
          dataset = rasterio.open(path)
          meta = dataset.meta
          with rasterio.open(os.path.join(dir,fileName), 'w', **meta) as dst:
            print("Writing to file...")
            rolled_array = np.rollaxis(np.float32(array[i]), axis=2)
            dst.write(rolled_array)
        break

startTime = time.perf_counter()
Y_pred = model.predict(X_test)
stopTime = time.perf_counter()

print(stopTime - startTime)
print("Shape of X_test:",X_test.shape)


"""### Accuracy Assesments"""

threshold = 0.7

"""####IoU loss"""

IOU= True

name_model = 'resunet_iou'

if IOU:
  early = tk.callbacks.EarlyStopping(monitor='val_loss', min_delta=1e-4, patience=10)
  save = tk.callbacks.ModelCheckpoint('%s.h5'%name_model, save_best_only=True)
  reduce = tk.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.1, patience=5)

  loss=hybrid_loss
  optimizer=tk.optimizers.Adam(lr=5e-4)

if IOU:

  tf.keras.backend.clear_session()
  model = get_resunet()
  model.compile(
      optimizer=optimizer,
      loss=loss,
      metrics=['accuracy'],
  )
  print("Training...")
  hist = model.fit(
      X_train, Y_train, 
      batch_size=5, 
      epochs=100, 
      verbose=1, 
      validation_data=(X_val, Y_val), 
      callbacks=[reduce, early, save], 
      shuffle=True
  )
  print("Final loss: ", hist.history['val_loss'][-1])
  print("Num epochs; ", len(hist.history['val_loss']))

if IOU:
  
  plt.rcParams.update({'font.size': 13,'font.family': 'serif'})
  plt.title("a)", loc='left')
  plt.ylabel("Total Loss")
  plt.xlabel("Epoch")
  plt.plot(hist.history['loss'],label = "Training")
  plt.plot(hist.history['val_loss'], label = "Validation")
  plt.legend()
  #plt.show()



if IOU:
  Y_pred = model.predict(X_test)

if IOU:
  for i in range(5):
      fig, ax = plt.subplots(1, 3, figsize=(21, 7))
      ax[0].imshow(inverse_convert(X_test[i]))
      ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
      ax[1].set_title('predicted')
      ax[2].imshow(Y_test[i, :, :, 0], cmap=plt.cm.gray)
      ax[2].set_title('labeled')
      #plt.show()


print("Generating Classification...")
i = 3
fig, ax = plt.subplots(1, 3, figsize=(28, 7))
plt.rcParams.update({'font.size': 30})
data = np.random.randn(30, 30)


ax[0].set_title('a)     Input      ')
ax[0].set_xticks([])
ax[0].set_yticks([])
ax[0].imshow(inverse_convert(X_test[i]))
ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
psm = ax[1].pcolormesh(Y_pred[i, :, :, 0],rasterized=True, vmin=0, vmax=1)
fig.colorbar(psm, ax=ax[1])
ax[1].set_title('b)    Predicted    ')
ax[1].set_xticks([])
ax[1].set_yticks([])
#ax[1].legend()
ax[2].imshow(Y_test[i, :, :, 0], cmap=plt.cm.gray)
ax[2].set_title('c)    Ground Truth    ')
ax[2].set_xticks([])
ax[2].set_yticks([])
plt.savefig('Classification.png',dpi=300)
plt.clf()
#plt.show()
print(" Done..")

def thresholdArray(array):
  newArr = np.copy(array).ravel()
  row = len(newArr)
  for i in range(row):
      if newArr[i] < threshold:
        newArr[i] = 0
      else:
        newArr[i] = 1
  return newArr

if IOU:


  Ave =0
  num = 0
  for i in range(30):
     
      IoUOut = jaccard_score(Y_test[i, :, :, 0].ravel(),thresholdArray(Y_pred[i, :, :, 0].ravel()), average='micro')
      
      if IoUOut != 0:
        Ave= Ave + IoUOut
        num+=1
        
  print('Average IOU:', Ave / num)

"""#### BER"""

BER= True #@param {type:"boolean"}

#Alex's Code from Metric.zip
if BER:

  def ber(label, logit):
      mat= confusion_matrix(label, logit)
      if len(mat) == 1:
        return -1
      TN, FP, FN, TP = mat.ravel()
      W = len(label)
      NP = sum(label)
      NN = W ** 2 - NP
      BER = (1 - .5 * (TP / NP + TN / NN))
      if TP == 0:
        if NP == 1.0:
          BER = 0
        else:
          BER = None
      
      return BER

if BER:
 

  AveBer = []
  for i in range(0,50):
      #fig, ax = plt.subplots(1, 3, figsize=(21, 7))
      berOut = ber(Y_test[i, :, :, 0].ravel(),thresholdArray(Y_pred[i, :, :, 0].ravel()))
      if berOut is not None: 
        AveBer.append(berOut)
      #AveBer = AveBer + berOut
      #print('BER:', berOut)
      #ax[0].imshow(inverse_convert(X[i]))
      #ax[1].imshow(thresholdArray(Y_pred[i, :, :, 0]), vmin=0, vmax=1)
      #ax[1].set_title('predicted')
      #ax[2].imshow(Y[i, :, :, 0],cmap=plt.cm.gray)
      #ax[2].set_title('labeled')
      ##plt.show()
  print('Average BER:', sum(AveBer) / len(AveBer))

"""#### Precision"""

Precision= True #@param {type:"boolean"}


if Precision:
  Ave = 0
  for i in range(50):
      #fig, ax = plt.subplots(1, 3, figsize=(21, 7))
      precOut = precision_score(Y_test[i, :, :, 0].ravel(), thresholdArray(Y_pred[i, :, :, 0].ravel()), average='micro')
      Ave = Ave + precOut
      #print('Accuracy Score:', accOut)
      #ax[0].imshow(inverse_convert(X_test[i]))
      #ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
      #ax[1].set_title('predicted')
      #ax[2].imshow(Y_test[i, :, :, 0],cmap=plt.cm.gray)
      #ax[2].set_title('labeled')
      ##plt.show()
  print('Average Score:', Ave / (i+1))

"""#### Recall"""

Recall= True #@param {type:"boolean"}


if Recall:
  Ave = 0
  for i in range(50):
      #fig, ax = plt.subplots(1, 3, figsize=(21, 7))
      RecallOut = recall_score(Y_test[i, :, :, 0].ravel(),thresholdArray(Y_pred[i, :, :, 0].ravel()),average='micro')
      Ave = Ave + RecallOut
      #print('Accuracy Score:', accOut)
      #ax[0].imshow(inverse_convert(X_test[i]))
      #ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
      #ax[1].set_title('predicted')
      #ax[2].imshow(Y_test[i, :, :, 0],cmap=plt.cm.gray)
      #ax[2].set_title('labeled')
      ##plt.show()
  print('Average Score:', Ave / (i+1))

"""#### F1"""

F1= True #@param {type:"boolean"}


if F1:
  Ave = 0
  for i in range(50):
      #fig, ax = plt.subplots(1, 3, figsize=(21, 7))
      fOut = f1_score(Y_test[i, :, :, 0].ravel(),thresholdArray(Y_pred[i, :, :, 0].ravel()),average='micro')
      Ave = Ave + fOut
      #print('Accuracy Score:', accOut)
      #ax[0].imshow(inverse_convert(X_test[i]))
      #ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
      #ax[1].set_title('predicted')
      #ax[2].imshow(Y_test[i, :, :, 0],cmap=plt.cm.gray)
      #ax[2].set_title('labeled')
      ##plt.show()
  print('Average Score:', Ave / (i+1))

"""#### Acuracy Score"""

AccuracyScore= True


def accuracy_score(label, logit):
    con = confusion_matrix(label.ravel(), logit.ravel()).ravel()
    if len(con) == 4:
      TN, FP, FN, TP = con
      ACC = (TP + TN) / (TN + FP + FN + TP)
      return ACC * 100
    else:
      return -1

if AccuracyScore:
  Ave = 0
  num =0
  for i in range(50):
      #fig, ax = plt.subplots(1, 3, figsize=(21, 7))
      accOut = accuracy_score(Y_test[i, :, :, 0].ravel(),thresholdArray(Y_pred[i, :, :, 0].ravel()))
      if accOut != -1:
        Ave = Ave + accOut
        num +=1
      #print('Accuracy Score:', accOut)
      #ax[0].imshow(inverse_convert(X_test[i]))
      #ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
      #ax[1].set_title('predicted')
      #ax[2].imshow(Y_test[i, :, :, 0],cmap=plt.cm.gray)
      #ax[2].set_title('labeled')
      ##plt.show()
  print('Average Score:', Ave / (num))

"""#### AUC-ROC"""

AUC_ROC= True


if AUC_ROC:
  
  for i in range(2):
      fig, ax = plt.subplots(1, 4, figsize=(24, 6))
      X_auc,Y_auc,Thresh = roc_curve(Y_test[i, :, :, 0].ravel(), Y_pred[i, :, :, 0].ravel())
      try:
        score = roc_auc_score(Y.ravel(),Y_pred.ravel(), average='macro', sample_weight=None, max_fpr=None, multi_class='raise', labels=None)
      except ValueError:
        score = 0
        print("No Labels present")
      print("AUC score", score)
      ax[0].imshow(inverse_convert(X[i]))
      ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
      ax[1].set_title('predicted')
      ax[2].imshow(Y[i, :, :, 0],cmap=plt.cm.gray)
      ax[2].set_title('labeled')
      ax[3].plot(X_auc,Y_auc)
      ##plt.show()



"""### Mosaic"""

Mosaic = False

GenerateSpecificMask = False
SpecificMask = 2

path_mosaic = 'mosaic'


if Mosaic:
    #X_mos, Y_mos = getData('mosaic', b_shuffle= False, ratio_shrink=3)
    Y_pred_mos = model.predict(X_test)

if Mosaic:
  for i in range(5):
      fig, ax = plt.subplots(1, 3, figsize=(21, 7))
      #ax[0].imshow(inverse_convert(X_mos[i]))
      ax[0].imshow(inverse_convert(X_test[i]))
      ax[1].imshow(Y_pred_mos[i, :, :, 0], vmin=0, vmax=1)
      ax[1].set_title('predicted')
      #ax[2].imshow(Y_mos[i, :, :, 0],cmap=plt.cm.gray)
      ax[2].imshow(Y_test[i, :, :, 0],cmap=plt.cm.gray)
      ax[2].set_title('labeled')
      ##plt.show()

#Mosaic the image

def mosaicImages(test):
  #new_im = Image.fromarray(np.uint8(test[10, :, :, 0]))

  new_im = Image.new('F', (5000,5000))
  indx = 0
  for x in range(5):
    for y in range(5):
      image = (test[indx, :, :, 0] * 255 / np.max(test[indx, :, :, 0])).astype('uint8')
      temp = Image.fromarray(image)
      temp = temp.resize((1000,1000))
      new_im.paste(temp,(x*1000,y*1000))
      indx = indx + 1
  return new_im

def adjustSpecMask(mask):
  newArr = np.copy(mask)
  #row = newArr.shape
  for i in range(25000000):
    if newArr[i] != 0:
      newArr[i] = 1
    else:
      newArr[i] = 0
  return newArr


if Mosaic:
  
  COLOR = 'black'
  plt.rcParams['text.color'] = COLOR
  plt.rcParams['axes.labelcolor'] = COLOR
  plt.rcParams['xtick.color'] = COLOR
  plt.rcParams['ytick.color'] = COLOR
  
  plt.rcParams.update({'font.size': 12})
  custom_lines = [Line2D([0], [0], color='b', lw=4),
                  Line2D([0], [0], color='g', lw=4),
                  Line2D([0], [0], color='r', lw=4),
                  Line2D([0], [0], color='y', lw=4),
                  Line2D([0], [0], color='w', lw=4)]

  #AUC_AVE_MOS_X,AUC_AVE_MOS_Y, AVE_SCORE_MOS
  for i, fname in enumerate(['Lonoke64','Lonoke65','Lonoke66','Lonoke67','Lonoke68']):
      fig, ax = plt.subplots(1, 4, figsize=(20, 5))

      img = plt.imread(f'{path_mosaic}/{fname}.tif')
      label = arr_color[plt.imread(f'{path_mosaic}/{fname}_Mask.tif')]
      
      mask  = plt.imread(f'{path_mosaic}/{fname}_Mask.tif')
      
      ax[0].set_title(f'{fname}.tif')
      ax[0].set_xticks([], [])
      ax[0].set_yticks([], [])
      ax[0].imshow(img)
      mos  = mosaicImages(Y_pred_mos[25*i:])
      mos.save("drive/My Drive/" + fname + "_Pred.tif")
      ax[1].imshow(mos)
      ax[1].set_title('mosaic')
      ax[1].set_xticks([], [])
      ax[1].set_yticks([], [])
      
      ax[2].imshow(label)
      
      
      ax[2].set_yticks([], [])
      ax[2].set_title('label')
      ax[2].set_xticks([], [])
      label = Image.fromarray(mask)
      
      label = np.array(label.getdata(0)).ravel()
      
      #label = np.resize(label,25000000)
      label = adjustSpecMask(label)
      mos      = np.array(mos)
      X,Y,Thresh = roc_curve(label, mos.ravel())
      score = roc_auc_score(label,mos.ravel(), average='macro', sample_weight=None, max_fpr=None, multi_class='raise', labels=None)
      if fname == 'Lonoke64':
        AUC_AVE_MOS_X,AUC_AVE_MOS_Y = X,Y
        AVE_SCORE_MOS = score
      else:
        AUC_AVE_MOS_X = AUC_AVE_MOS_X + X
        AUC_AVE_MOS_Y = AUC_AVE_MOS_Y + Y
        AVE_SCORE_MOS += score
      
      score = "AUC score:" + str(auc(X,Y))
      score = score[:15]
      ax[3].annotate(score, (0.5,0.25))
      ax[3].plot(X,Y)
      #plt.savefig(f"drive/My Drive/Crop Contour/Descriptive Figures/AUC-ROC/{fname}.png")
      ##plt.show()

def thresholdRavel(array):
  newArr = np.copy(array)
  row = newArr.shape
  row = row[0]
  for i in range(row):
    if newArr[i] < threshold:
      newArr[i] = 0
    else:
      newArr[i] = 1
  return newArr


if Mosaic:

  try:
      shutil.rmtree(path_mosaic)
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))

"""#### Sensitivity Testing"""

sensitivityTest = True
ratio = 0.3

def addNoise(filename,ratioIn):

  img = cv2.imread(filename)
  gauss = np.random.normal(0,ratioIn,img.size)
  gauss = gauss.reshape(img.shape[0],img.shape[1],img.shape[2]).astype('uint8')
  noise = img + img * gauss
  noise = cv2.cvtColor(noise, cv2.COLOR_BGR2RGB)
  noise = Image.fromarray(noise)
  noise.save(filename)

def noisify(ratio):

  #lifImgPath = "drive/My Drive/Crop Contour/Greene- Feb 2020"
  lifImgPath = path_label
  
  trainImgPath = path_sensitivity

  outsize = 960
  names = os.listdir(lifImgPath)
  #print(names)
  for fnameAll in names:
      fname0 = os.path.splitext(os.path.split(fnameAll)[-1])[0]
      inLif = os.path.join(lifImgPath, fname0 + ".lif")
      print(inLif)
      outImg  = os.path.join(trainImgPath, fname0 + ".tif")
      outMask = os.path.join(trainImgPath, fname0 + "_Mask.tif")
      
      imgs_masks_from_lif(
            inLif,
            dstImg=outImg,
            dstMask=outMask
        )
      
      
      addNoise(outImg,ratio)
      if Grayscale:
            gray(outImg)

      spatial_subset_image(
            outImg, outsize, 
            os.path.join(trainImgPath, 'img', fname0)
        )
      spatial_subset_image(
            outMask, outsize, 
            os.path.join(trainImgPath, 'label', fname0 + "_Mask"),
            sBand=1
        )


#Create New Directory for Lower Resolutions

if sensitivityTest:

  path_sensitivity = 'SensitivityTest'
  if not os.path.isdir(path_sensitivity):
    os.mkdir(path_sensitivity)
  if not os.path.isdir(os.path.join(path_sensitivity, 'img')):
    os.mkdir(os.path.join(path_sensitivity, 'img'))
  if not os.path.isdir(os.path.join(path_sensitivity, 'label')):
    os.mkdir(os.path.join(path_sensitivity, 'label'))
  noisify(ratio)

createDir('data',path_label)

def mosaicColor(test):
  #new_im = Image.fromarray(np.uint8(test[10, :, :, 0]))

  new_im = Image.new('RGB', (5000,5000))
  indx = 0
  for x in range(5):
    for y in range(5):
      image = inverse_convert(test[indx])
      temp = Image.fromarray(image)
      temp = temp.resize((1000,1000))
      new_im.paste(temp,(x*1000,y*1000))
      indx = indx + 1
  return new_im

if sensitivityTest:


    X_sens_img, Y_sens_img = getData('SensitivityTest', b_shuffle= False, ratio_shrink=3)
    X_sens_img_test, Y_sens_img_test = X_sens_img[idx_test], Y_sens_img[idx_test]

    X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
    X_test, Y_test = X[idx_test], Y[idx_test]

    del X_sens_img, Y_sens_img 
    del X, Y


    Y_pred_sens = model.predict(X_sens_img_test)
    Y_pred = model.predict(X_test)

    for i in range(5):
        fig, ax = plt.subplots(1, 5, figsize=(21, 7))
        ax[0].imshow(inverse_convert(X_test[i]))
        ax[0].set_title('Normal Image')
        ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
        ax[1].set_title('True Prediction')
        ax[2].imshow(inverse_convert(X_sens_img_test[i]))
        ax[2].set_title('Lower Res Image')
        ax[3].imshow(Y_pred_sens[i, :, :, 0], vmin=0, vmax=1)
        ax[3].set_title('Lower Resolution Prediction')
        ax[4].imshow(Y_sens_img_test[i, :, :, 0],cmap=plt.cm.gray)
        ax[4].set_title('labeled')
        ##plt.show()

#AUC Curve for S&P noise
if sensitivityTest:
  X_SENSE, Y_SENSE, Thresh_SENSE = roc_curve(Y_sens_img_test.ravel(), Y_pred_sens.ravel())

  #del Y_sens_img_test , X,Y,
  #del Y_pred_sens


  #df = pd.DataFrame(columns=range(127021))

  #df.append(pd.Series(X_SENSE,df.columns),ignore_index=True)
  #df.append(pd.Series(Y_SENSE,name = 'Sensitivity-Y'),ignore_index=True) 
  #df.to_csv('drive/My Drive/AUCassessments.csv')

  print('Average Score',auc(X_SENSE,Y_SENSE))

  fig, ax = plt.subplots(1, 1, figsize=(6, 6))

  ax.plot(X_SENSE,Y_SENSE)
  #plt.show()




try:
    shutil.rmtree('data')
    shutil.rmtree('SensitivityTest')
except OSError as e:
    print("Error:")

createDir('data',path_label)
if sensitivityTest:

  path_sensitivity = 'SensitivityTest'
  if not os.path.isdir(path_sensitivity):
    os.mkdir(path_sensitivity)
  if not os.path.isdir(os.path.join(path_sensitivity, 'img')):
    os.mkdir(os.path.join(path_sensitivity, 'img'))
  if not os.path.isdir(os.path.join(path_sensitivity, 'label')):
    os.mkdir(os.path.join(path_sensitivity, 'label'))
  ratio = 0.4
  noisify(ratio)

if sensitivityTest:
  try:
      shutil.rmtree('data')
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))

createDir('data',path_label)

if sensitivityTest:


    X_sens_img, Y_sens_img = getData('SensitivityTest', b_shuffle= False, ratio_shrink=3)
    X_sens_img_test, Y_sens_img_test = X_sens_img[idx_test], Y_sens_img[idx_test]

    X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
    X_test, Y_test = X[idx_test], Y[idx_test]

    del X_sens_img, Y_sens_img 
    del X, Y


    Y_pred_sens = model.predict(X_sens_img_test)
    Y_pred = model.predict(X_test)
    X_SENSE2, Y_SENSE2, Thresh_SENSE = roc_curve(Y_sens_img_test.ravel(), Y_pred_sens.ravel())




if sensitivityTest:
  try:
      shutil.rmtree('data')
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))
createDir('data',path_label)

"""####Cloud Testing"""

ratio = 0.6

def Cloudify():

  #lifImgPath = "drive/My Drive/Crop Contour/Greene- Feb 2020"
  lifImgPath = path_label
  
  trainImgPath = path_sensitivity

  outsize = 960
  names = os.listdir(lifImgPath)
  #print(names)
  for fnameAll in names:
      fname0 = os.path.splitext(os.path.split(fnameAll)[-1])[0]
      inLif = os.path.join(lifImgPath, fname0 + ".lif")
      print(inLif)
      outImg  = os.path.join(trainImgPath, fname0 + ".tif")
      outMask = os.path.join(trainImgPath, fname0 + "_Mask.tif")
      
      imgs_masks_from_lif(
            inLif,
            dstImg=outImg,
            dstMask=outMask
        )

      aug = iaa.Alpha(factor = ratio, first = iaa.Clouds())
      img = cv2.imread(outImg)
      img = aug(image = img)
      img = Image.fromarray(img)
      img.save(outImg)
      if Grayscale:
            gray(outImg)

      spatial_subset_image(
            outImg, outsize, 
            os.path.join(trainImgPath, 'img', fname0)
        )
      spatial_subset_image(
            outMask, outsize, 
            os.path.join(trainImgPath, 'label', fname0 + "_Mask"),
            sBand=1
        )

def clearSensitivity():


  if not os.path.isdir(path_sensitivity):
    os.mkdir(path_sensitivity)
  if not os.path.isdir(os.path.join(path_sensitivity, 'img')):
    os.mkdir(os.path.join(path_sensitivity, 'img'))
  if not os.path.isdir(os.path.join(path_sensitivity, 'label')):
    os.mkdir(os.path.join(path_sensitivity, 'label'))
  noisify(0)

if sensitivityTest: 
    clearSensitivity()
    Cloudify()
    X_cloud_img, Y_cloud_img = getData('SensitivityTest', b_shuffle= False, ratio_shrink=3)
    shutil.rmtree('SensitivityTest')
    X_cloud_img_test, Y_cloud_img_test = X_cloud_img[idx_test], Y_cloud_img[idx_test]

    del X_cloud_img, Y_cloud_img 

    Y_pred_cloud= model.predict(X_cloud_img_test)
    X_cloud,Y_cloud,Thresh_cloud = roc_curve(Y_cloud_img_test.ravel(), Y_pred_cloud.ravel())
    for i in range(5):
        fig, ax = plt.subplots(1, 5, figsize=(21, 7))
        ax[0].imshow(inverse_convert(X_test[i]))
        ax[0].set_title('Normal Image')
        ax[1].imshow(Y_pred[i, :, :, 0], vmin=0, vmax=1)
        ax[1].set_title('True Prediction')
        ax[2].imshow(inverse_convert(X_cloud_img_test[i]))
        ax[2].set_title('Lower Res Image')
        ax[3].imshow(Y_pred_cloud[i, :, :, 0], vmin=0, vmax=1)
        ax[3].set_title('Lower Resolution Prediction')
        ax[4].imshow(Y_cloud_img_test[i, :, :, 0],cmap=plt.cm.gray)
        ax[4].set_title('labeled')
        ##plt.show()
    #del X_cloud_img_test, Y_cloud_img_test

if sensitivityTest:
  path_sensitivity = 'SensitivityTest'
  try:
      shutil.rmtree(path_sensitivity)
  except OSError as e:
      print("Error: %s : ")

if sensitivityTest:
  ratio = 0.7
  clearSensitivity()
  Cloudify()
  X_cloud_img, Y_cloud_img = getData('SensitivityTest', b_shuffle= False, ratio_shrink=3)
  shutil.rmtree('SensitivityTest')
  X_cloud_img_test2, Y_cloud_img_test2 = X_cloud_img[idx_test], Y_cloud_img[idx_test]

  del X_cloud_img, Y_cloud_img 

  Y_pred_cloud2= model.predict(X_cloud_img_test2)
  X_cloud2,Y_cloud2,Thresh_cloud = roc_curve(Y_cloud_img_test2.ravel(), Y_pred_cloud2.ravel())

if sensitivityTest:
  fig, ax = plt.subplots(1, 1, figsize=(12, 12))
  ax.imshow(inverse_convert(X_cloud_img_test[4]))

  fig, ax = plt.subplots(1, 2, figsize=(12, 6))


  X_cloud,Y_cloud,Thresh_cloud = roc_curve(Y_cloud_img_test.ravel(), Y_pred_cloud.ravel())
  #del Y_cloud_img_test, Y_pred_cloud

  X_norm , Y_norm, Thresh_norm = roc_curve(Y_test.ravel(), Y_pred.ravel())

  print("Normal AUC Score", auc(X_norm,Y_norm))
  print("Cloud AUC score", auc(X_cloud,Y_cloud))


  ax[0].plot(X_norm,Y_norm)
  ax[1].plot(X_cloud,Y_cloud)
  ##plt.show()

"""#### Resampling"""

Resample = True
ratio = 2

path_resample= 'Resample'

if Resample:
  try:
      shutil.rmtree('data')
  except OSError as e:
      print("Error: %s : %s" )

if Resample:
  createDir('data',path_label)

def rasterResample(ratio):
  names = os.listdir('Resample/img')
  print(names)
  for i in names:
    s = 'Resample/img/'+ i
    #print(s)
    img = Image.open(s)
    arr = np.array(img.copy())
    img = np.array(img)
    for i in range(0,arr.shape[0],ratio):
        for j in range(0,arr.shape[1],ratio):
            arr[i:i+ratio-1,j:j+ratio-1] = np.mean(img[i:i+ratio-1,j:j+ratio-1])
    img = Image.fromarray(arr)
    img.save(s)


if Resample:
  createDir('Resample',path_label)

if Resample:
  rasterResample(10)
  X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
  X_test, Y_test = X[idx_test], Y[idx_test]
  X_resample_2_img, Y_resample_2_img = getData(path_resample, b_shuffle= False, ratio_shrink=3)
  X_resample_2_img_test, Y_resample_2_img_test = X_resample_2_img[idx_test], Y_resample_2_img[idx_test]
  Y_pred = model.predict(X_test)

  Y_pred_resample_2 = model.predict(X_resample_2_img_test)

if Resample:

  #resample('Lonoke64.tif',ratio)
  fig, ax = plt.subplots(1, 2, figsize=(21, 7))
  ax[0].imshow(inverse_convert(X[i]))
  ax[0].set_title('Normal Image')
  ax[1].imshow(inverse_convert(X_resample_2_img[i]))
  ax[1].set_title('Resampled')
  ###plt.show()

if Resample:

  fig, ax = plt.subplots(1, 1, figsize=(6, 6))
  X_no,Y_no,Thresh_no = roc_curve(Y_test.ravel(), Y_pred.ravel())
  X_RE_2,Y_RE_2,Thresh_RE = roc_curve(Y_resample_2_img_test.ravel(), Y_pred_resample_2.ravel())

  print("AUC Resampled_10", auc(X_RE_2,Y_RE_2))
  print("AUC Normal", auc(X_no,Y_no))
  ax.plot(X_RE_2,Y_RE_2)
  ax.plot(X_no,Y_no)
  ##plt.show()

if Resample:
  try:
      shutil.rmtree('Resample')
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))

if Resample:
  createDir('Resample',path_label)



if Resample:
  rasterResample(20)
  X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
  X_test, Y_test = X[idx_test], Y[idx_test]
  X_resample_3_img, Y_resample_3_img = getData(path_resample, b_shuffle= False, ratio_shrink=3)
  X_resample_3_img_test, Y_resample_3_img_test = X_resample_3_img[idx_test], Y_resample_3_img[idx_test]
  Y_pred = model.predict(X_test)

  Y_pred_resample_3 = model.predict(X_resample_3_img_test)

if Resample:
  fig, ax = plt.subplots(1, 1, figsize=(6, 6))
  X_no,Y_no,Thresh_no = roc_curve(Y_test.ravel(), Y_pred.ravel())
  X_RE_3,Y_RE_3,Thresh_RE = roc_curve(Y_resample_3_img_test.ravel(), Y_pred_resample_3.ravel())

  print("AUC Resampled-30", auc(X_RE_3,Y_RE_3))
  print("AUC Normal", auc(X_no,Y_no))
  ax.plot(X_RE_3,Y_RE_3)
  ax.plot(X_no,Y_no)
  ##plt.show()

if Resample:
  try:
      shutil.rmtree('Resample')
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))

if Resample:
  createDir('Resample',path_label)



if Resample:
  rasterResample(30)
  X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
  X_test, Y_test = X[idx_test], Y[idx_test]
  X_resample_4_img, Y_resample_4_img = getData(path_resample, b_shuffle= False, ratio_shrink=3)
  X_resample_4_img_test, Y_resample_4_img_test = X_resample_4_img[idx_test], Y_resample_4_img[idx_test]
  Y_pred = model.predict(X_test)

  Y_pred_resample_4 = model.predict(X_resample_4_img_test)


if Resample:
  fig, ax = plt.subplots(1, 1, figsize=(6, 6))
  X_no,Y_no,Thresh_no = roc_curve(Y_test.ravel(), Y_pred.ravel())
  X_RE_4,Y_RE_4,Thresh_RE = roc_curve(Y_resample_4_img_test.ravel(), Y_pred_resample_4.ravel())
  print("AUC Resampled-60", auc(X_RE_4,Y_RE_4))
  print("AUC Normal", auc(X_no,Y_no))
  ax.plot(X_RE_4,Y_RE_4)
  ax.plot(X_no,Y_no)
  ##plt.show()

if Resample:
  try:
      shutil.rmtree('Resample')
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))

if Resample:
  createDir('Resample',path_label)



if Resample:
  rasterResample(60)
  X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
  X_test, Y_test = X[idx_test], Y[idx_test]
  X_resample_5_img, Y_resample_5_img = getData(path_resample, b_shuffle= False, ratio_shrink=3)
  X_resample_5_img_test, Y_resample_5_img_test = X_resample_5_img[idx_test], Y_resample_5_img[idx_test]
  Y_pred = model.predict(X_test)

  Y_pred_resample_5 = model.predict(X_resample_5_img_test)

if Resample:
  fig, ax = plt.subplots(1, 1, figsize=(6, 6))
  X_no,Y_no,Thresh_no = roc_curve(Y_test.ravel(), Y_pred.ravel())
  X_RE_5,Y_RE_5,Thresh_RE = roc_curve(Y_resample_5_img_test.ravel(), Y_pred_resample_5.ravel())
  print("AUC Resampled", auc(X_RE_5,Y_RE_5))
  print("AUC Normal", auc(X_no,Y_no))
  ax.plot(X_RE_5,Y_RE_5)
  ax.plot(X_no,Y_no)
  ###plt.show()

  try:
      shutil.rmtree('Resample')
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))

  if Resample:
    createDir('Resample',path_label)



if Resample:
  rasterResample(60)
  X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
  X_test, Y_test = X[idx_test], Y[idx_test]
  X_resample_6_img, Y_resample_6_img = getData(path_resample, b_shuffle= False, ratio_shrink=3)
  X_resample_6_img_test, Y_resample_6_img_test = X_resample_6_img[idx_test], Y_resample_6_img[idx_test]
  Y_pred = model.predict(X_test)

  Y_pred_resample_6 = model.predict(X_resample_6_img_test)

if Resample:
  fig, ax = plt.subplots(1, 1, figsize=(6, 6))
  X_no,Y_no,Thresh_no = roc_curve(Y_test.ravel(), Y_pred.ravel())
  X_RE_6,Y_RE_6,Thresh_RE = roc_curve(Y_resample_6_img_test.ravel(), Y_pred_resample_5.ravel())
  print("AUC Resampled", auc(X_RE_6,Y_RE_6))
  print("AUC Normal", auc(X_no,Y_no))
  ax.plot(X_RE_6,Y_RE_6)
  ax.plot(X_no,Y_no)
  ##plt.show()
  try:
      shutil.rmtree('Resample')
  except OSError as e:
      print("Error: %s : %s" % (dir_path, e.strerror))



"""####Different Site"""

DiffSite= True

if DiffSite:

  path_diffSite = 'test'
  createDir(path_diffSite,path_55, fromLIF=False)

  X_diff, Y_diff = getData('test', b_shuffle= False, ratio_shrink=3, test=True)
  
  Y_diff = np.zeros((X_diff.shape[0],320,320,1))
  predictionsList = []
  for i, x in enumerate(np.array(sorted(glob(os.path.join('test', 'label', '*.tif'))))):
    predictionsList.append(x.replace('label','img'))
    img = Image.open(x)
    array = np.asarray(img)
    array = array[::3,::3]
    array = np.reshape(array,(320,320,1))
    Y_diff[i] = array
  print("Shape Xdiff:", X_diff.shape)
  print("Shape Ydiff:", Y_diff.shape)
  print("Predictions List:", predictionsList)

  '''
  #Save img
  for i in predictionsList:
    file = i.replace("_Mask_Mask","_Mask")
    img = Image.open(file)
    base = os.path.basename(file)
    img.save("55tiles/Img/" + base)

  #Save Label
  for i in predictionsList:
    img = Image.open(i.replace("img","label"))
    base = os.path.basename(i)
    img.save("55tiles/label/" + base)

  #Save Prediction
  print(predictionsList)
  '''
  Y_pred_diff = model.predict(X_diff)
  print(Y_pred_diff.shape)
  '''
  for x,i in enumerate(predictionsList):
    file = i.replace('_Mask_Mask',"_pred")
    img = Image.fromarray(Y_pred_diff[x,:,:,0], 'F')
    base = os.path.basename(file)
    img.save("/Volumes/Research/CropContour/ConvertedPredictions/" + base)
  '''
  print("Diff AUC Score:", roc_auc_score(Y_diff.ravel(), Y_pred_diff.ravel()))
  X_DIFF,Y_DIFF,Thresh_RE = roc_curve(Y_diff.ravel(), Y_pred_diff.ravel())
  print("X_DIFF",X_DIFF)
  print("Y_DIFF",Y_DIFF)
  overallDiffAUC = auc(X_DIFF,Y_DIFF)
  print("Overall AUC Diff:", overallDiffAUC)

  countyList = ['Arkansas', 'Clay', 'Craighead', 'Crittenden', 'Desha', 'Greene', "Jackson", 'Jefferson', 'Lawrence', 'Mississippi', 'Woodruff']

  

  CountyMax_AUC = overallDiffAUC
  CountyMin_AUC = overallDiffAUC

  CountyMax_Name = ''
  CountyMin_Name = ''

  X_CountyMax,Y_CountyMax = 0,0
  X_CountyMin,Y_CountyMin = 0,0
  AUC_dict = {}
  ACC_dict = {}
  BER_dict = {}
  IOU_dict = {}
  F1_dict  = {}
  def ber(label, logit):
      mat= confusion_matrix(label.ravel(), logit.ravel())
      if len(mat) == 1:
        return -1
      TN, FP, FN, TP = mat.ravel()
      W = label.shape[0]
      NP = label.sum()
      NN = W ** 2 - NP
      BER = (1 - .5 * (TP / NP + TN / NN)) * 100
      if TP == 0:
        if NP == 1.0:
          BER = 0
        else: #Test after running for validity
          BER = -1
      
      return BER

  for num,i in enumerate(countyList):
    X_county = np.zeros((125,320,320,3))
    Y_county = np.zeros((125,320,320,1))
    print("Getting images...")

    for j, file in enumerate(sorted(glob('/Users/dakota/Documents/UARK/CropContour/Code/55TilesTest/test/img/AR_' + i +"*.tif"))):
      #print(file)
      img = tk.preprocessing.image.load_img(file)
      array = tk.preprocessing.image.img_to_array(img)
      array = array.copy()
      array = array[::3,::3]
      array = array[:, :, ::-1]
      array[:, :, 0] -= MEAN_B
      array[:, :, 1] -= MEAN_G
      array[:, :, 2] -= MEAN_R
      array = np.asarray(array)
      
      array = np.reshape(array,(320,320,3))
      X_county[j] = array
    print("Getting Labels...")
    for j, file in enumerate(sorted(glob('/Users/dakota/Documents/UARK/CropContour/Code/55TilesTest/test/label/AR_' + i +"*.tif"))):
      #print(file)
      img = Image.open(file)
      array = np.asarray(img)
      array = array[::3,::3]
      array = np.reshape(array,(320,320,1))
      Y_county[j] = array
    
    X_county = X_diff[num*125:(num+1)*125,:,:,:]
    Y_county = Y_diff[num*125:(num+1)*125,:,:,:]
    Y_pred_county = model.predict(X_county)

    print("Diff Acc")

    ACC_dict[i] = accuracy_score(Y_county.ravel(),thresholdArray(Y_pred_county.ravel()))
    print("Diff F1")
    
    F1_dict[i] = f1_score(Y_county.ravel(),thresholdArray(Y_pred_county.ravel()))

    print("Diff IOU")

    IOU_dict[i] = jaccard_score(Y_county.ravel(),thresholdArray(Y_pred_county.ravel()))

    print("Diff BER")
    BER_dict[i] = ber(Y_county,thresholdArray(Y_pred_county))


    
    X_DIFF_county,Y_DIFF_county,Thresh_RE = roc_curve(Y_county.ravel(), Y_pred_county.ravel())
    print("AUC of ", i, ": ",auc(X_DIFF_county,Y_DIFF_county) )
    AUC_dict[i] = auc(X_DIFF_county,Y_DIFF_county)
  
    if i == "Arkansas":
      CountyMin_AUC = auc(X_DIFF_county,Y_DIFF_county)
      CountyMin_Name = i
      X_CountyMin, Y_CountyMin = X_DIFF_county,Y_DIFF_county

      CountyMax_AUC = auc(X_DIFF_county,Y_DIFF_county)
      CountyMax_Name = i
      X_CountyMax,Y_CountyMax = X_DIFF_county,Y_DIFF_county

    if auc(X_DIFF_county,Y_DIFF_county) > CountyMax_AUC:
      CountyMax_AUC = auc(X_DIFF_county,Y_DIFF_county)
      CountyMax_Name = i
      X_CountyMax,Y_CountyMax = X_DIFF_county,Y_DIFF_county
    elif auc(X_DIFF_county,Y_DIFF_county) < CountyMin_AUC:
      CountyMin_AUC = auc(X_DIFF_county,Y_DIFF_county)
      CountyMin_Name = i
      X_CountyMin, Y_CountyMin = X_DIFF_county,Y_DIFF_county
   


  print("Max County: ", CountyMax_Name, " AUC:", CountyMax_AUC)
  print("Min County: ", CountyMin_Name, " AUC:", CountyMin_AUC)

  print(AUC_dict)




top = cm.get_cmap('RdGy_r', 128)
bottom = cm.get_cmap('YlGn', 128)


newcolors = np.vstack((top(np.linspace(0.05, 0.5, 128)),
                       bottom(np.linspace(0, 1, 128))))
newcmp = ListedColormap(newcolors, name='Fields')


"""#### Final Assessment"""

try:
      shutil.rmtree('data')
except:
      print("Error")
createDir('data',path_label)


X, Y = getData('data', b_shuffle= False, ratio_shrink=3)
X_test, Y_test = X[idx_test], Y[idx_test]
Y_pred = model.predict(X_test)
X_norm , Y_norm, Thresh_norm = roc_curve(Y_test.ravel(), Y_pred.ravel())

if not os.path.isdir('Graphs'):
    os.mkdir('Graphs')

if not os.path.isdir('Graphs/AUCarrays'):
    os.mkdir('Graphs/AUCarrays')
#-------Save arrays-----------
np.save('Graphs/AUCarrays/X_norm.npy',X_norm)
np.save('Graphs/AUCarrays/Y_norm.npy',Y_norm)

np.save('Graphs/AUCarrays/X_RE_2.npy',X_RE_2)
np.save('Graphs/AUCarrays/Y_RE_2.npy',Y_RE_2)

np.save('Graphs/AUCarrays/X_RE_3.npy',X_RE_3)
np.save('Graphs/AUCarrays/Y_RE_3.npy',Y_RE_3)

np.save('Graphs/AUCarrays/X_RE_4.npy',X_RE_4)
np.save('Graphs/AUCarrays/Y_RE_4.npy',Y_RE_4)

np.save('Graphs/AUCarrays/X_RE_5.npy',X_RE_5)
np.save('Graphs/AUCarrays/Y_RE_5.npy',Y_RE_5)

np.save('Graphs/AUCarrays/X_cloud.npy',X_cloud)
np.save('Graphs/AUCarrays/Y_cloud.npy',Y_cloud)

np.save('Graphs/AUCarrays/X_cloud2.npy',X_cloud2)
np.save('Graphs/AUCarrays/Y_cloud2.npy',Y_cloud2)

np.save('Graphs/AUCarrays/X_SENSE.npy',X_SENSE)
np.save('Graphs/AUCarrays/Y_SENSE.npy',Y_SENSE)

np.save('Graphs/AUCarrays/X_SENSE2.npy',X_SENSE2)
np.save('Graphs/AUCarrays/Y_SENSE2.npy',Y_SENSE2)

np.save('Graphs/AUCarrays/X_DIFF.npy',X_DIFF)
np.save('Graphs/AUCarrays/Y_DIFF.npy',Y_DIFF)

np.save('Graphs/AUCarrays/X_CountyMax.npy',X_CountyMax)
np.save('Graphs/AUCarrays/Y_CountyMax.npy',Y_CountyMax)

np.save('Graphs/AUCarrays/X_CountyMin.npy',X_CountyMin)
np.save('Graphs/AUCarrays/Y_CountyMin.npy',Y_CountyMin)
