# CropContourLeveeMapping
## Overview
This is the code repository for the 2023 paper Dale et. al linked [here](https://www.sciencedirect.com/science/article/pii/S0168169923003423). 

Please note that the path to the data (_path_label_ and _path_55_) will need to be changed. 

Inside this repository you will find all of the code needed to generate the results presented in the paper, however, the data used is too large to add to the repository. 
Thus, you can find it [here](https://doi.org/10.5281/zenodo.8222696)

The primary file of this repository is `train.py`. This contains the code for both model training and sensitivity analysis.
The `AUC.ipynb` will generate the AUC graphs shown in the paper (figure 6) from the .npy files generated from `train.py`.
``comparisons.ipynb`` will generate the violin plot from the paper (figure 9) as well as any qualitative comparisons (figures 7 and 8).

## Environment
This project utilizes anaconda for its package management.

You may rebuild the environment with the following commands

```conda env create --name CropContour --file ENV.yml```

```conda activate CropContour```

## Contact Information
You will find contact information for the authors below.

### Dakota S. Dale
**Email**: dakotadale99@gmail.com

**LinkedIn**: https://www.linkedin.com/in/dakota-dale/

### Dr. Lu Liang
**Email**: lu.liang@unt.edu

**Website**: https://sites.google.com/site/liang3mlab/home

### Dr. Benjamin R. Runkle
**Email**: brrunkle@uark.edu

**LinkedIn**: https://www.linkedin.com/in/dr-benjamin-runkle/

**Website**: https://runkle.uark.edu/

## Citation
For citing this work, please use the below citation.
``` 

@article{DALE2023107954,
title = {Deep learning solutions for mapping contour levee rice production systems from very high resolution imagery},
journal = {Computers and Electronics in Agriculture},
volume = {211},
pages = {107954},
year = {2023},
issn = {0168-1699},
doi = {https://doi.org/10.1016/j.compag.2023.107954},
url = {https://www.sciencedirect.com/science/article/pii/S0168169923003423},
author = {Dakota S. Dale and Lu Liang and Liheng Zhong and Michele L. Reba and Benjamin R.K. Runkle},
keywords = {Remote sensing, Agriculture, Irrigation, ResNet}
}
```
