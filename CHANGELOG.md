# Release notes

<!-- do not remove -->

## 0.5.1

Fix the doc generation

## 0.5.0

New features:

Add CLI for temporal coherence estimation for DS

Add dispersion index calculation for PS

Add logic operation for pc index

Add `transform` for coordinate reprojection

Add holoviews plot


Maintain:

Using `with ... as:` to prevent dask cluster unclosed

Remove all plot options in CLI

Set all thread per worker for local cuda cluster to 1

Use progressbar

Update doc theme

Reorginaze Tutorial

## 0.4.2

Finish point cloud manipulation functions and commands

Add utils for automatically determine chunk_size

## 0.4.1

Fix a small deploy issue

## 0.4.0

Modify gamma load function for more precise look vector

Add point cloud manipulation

Add Introduction section and add more detail on readme

Add utils, logger.zarr_info logger.darr_info

Rename emperical_co_sp to emperical_co_pc

## 0.3.2

Modify the gamma load funtion to make it faster

## 0.3.1

Add DS processing from CLI tutorial and fix bugs

## 0.3.0

Add interface to load gamma result

## 0.2.0

Add ks_test, select_ds_can, emperical_co_sp, emi CLI

Add log and sparse utils

Add test script

## 0.1.0

Refine phase linking EMI

Add function to estimate temporal coherence

Add tutorial for dask processing

Update the test in API notebooks

## 0.0.4

Add covariance/coherence matrix estimation for sparse data

Add phase linking method: EMI

Add tutorial for DS processing (still under construction)

## 0.0.3

Add ks test

Add covariance/coherence matrix estimation

Add tutorial for adaptive multilooking

## 0.0.2

Remove cupy requirement for automatically publish to pypi

## 0.0.1




