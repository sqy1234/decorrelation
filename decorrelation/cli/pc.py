# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/CLI/pc.ipynb.

# %% auto 0
__all__ = ['de_idx2bool', 'de_bool2idx', 'de_ras2pc', 'console_de_ras2pc', 'de_pc2ras', 'de_pc_union', 'de_pc_intersect',
           'de_pc_diff', 'de_pc_logic_ras', 'de_pc_logic_pc', 'de_pc_select_data']

# %% ../../nbs/CLI/pc.ipynb 4
import logging
import zarr
import cupy as cp
import numpy as np
import numexpr as ne

import dask
from dask import array as da
from dask.distributed import Client, LocalCluster, progress

from ..pc import pc2ras, pc_union, pc_intersect, pc_diff
from .utils.logging import log_args, de_logger
from .utils.chunk_size import (get_pc_chunk_size_from_n_pc_chunk, 
                                                get_pc_chunk_size_from_pc_chunk_size, 
                                                get_pc_chunk_size_from_n_ras_chunk,
                                                get_ras_chunk_size_from_n_pc_chunk)

from fastcore.script import call_parse, Param

# %% ../../nbs/CLI/pc.ipynb 5
@call_parse
@log_args
@de_logger
def de_idx2bool(idx:str, # point cloud index
                is_pc:str, # output, output bool array
                shape:tuple, # shape of one image (nlines,width)
                az_chunk_size:int=None, # output azimuth chunk size, 
                n_az_chunk:int=None, # # output number of azimuth chunks
                r_chunk_size:int=None, # output range chunk size
                n_r_chunk:int=None, # output number of range chunks
):
    '''Convert pc index to bool 2d array'''
    logger = logging.getLogger(__name__)
    is_pc_path = is_pc

    idx_zarr = zarr.open(idx,mode='r')
    logger.zarr_info('idx',idx_zarr)
    assert idx_zarr.ndim == 2, "idx dimentation is not 2."
    logger.info('loading idx into memory.')
    idx = zarr.open(idx,mode='r')[:]

    logger.info('calculate the bool array')
    is_pc = np.zeros(shape,dtype=bool)
    is_pc[idx[0],idx[1]] = True

    chunks = get_ras_chunk_size_from_n_pc_chunk('idx','ras',idx_zarr.shape[1],idx_zarr.chunks[1],
                                               *shape,
                                               az_chunk_size=az_chunk_size,
                                               n_az_chunk=n_az_chunk,
                                               r_chunk_size=r_chunk_size,
                                               n_r_chunk=n_r_chunk,
                                              )
    is_pc_zarr = zarr.open(is_pc_path,'w',shape=shape,dtype=bool,chunks=chunks)
    logger.zarr_info('is_pc',is_pc_zarr)
    logger.info('write the bool array.')
    is_pc_zarr[:] = is_pc
    logger.info('write done.')

# %% ../../nbs/CLI/pc.ipynb 6
@call_parse
@log_args
@de_logger
def de_bool2idx(is_pc:str, # input bool array
                idx:str, # output, point cloud index
                pc_chunk_size:int=None, # output point chunk size
                n_pc_chunk:int=None, # output number of chunk
):
    '''Convert bool 2d array to integer index'''
    idx_path = idx
    logger = logging.getLogger(__name__)

    is_pc_zarr = zarr.open(is_pc,'r')
    logger.zarr_info('is_pc', is_pc_zarr)
    logger.info('loading is_pc into memory.')
    is_pc = zarr.open(is_pc,mode='r')[:]
    
    logger.info('calculate the index')
    idx = np.stack(np.where(is_pc))

    pc_chunk_size = get_pc_chunk_size_from_n_ras_chunk('is_pc','idx',
                                                       *is_pc_zarr.shape[:2],
                                                       *is_pc_zarr.chunks[:2],
                                                       idx.shape[1],
                                                       pc_chunk_size=pc_chunk_size, n_pc_chunk=n_pc_chunk)
    idx_zarr = zarr.open(idx_path,'w',shape=idx.shape,dtype=bool,chunks=(2,pc_chunk_size))
    logger.info('write the idx.')
    idx_zarr[:] = idx
    logger.info('write done.')

# %% ../../nbs/CLI/pc.ipynb 7
@log_args
@de_logger
def de_ras2pc(idx:str, # point cloud index
              ras:str|list, # path (in string) or list of path for raster data
              pc:str|list, # output, path (in string) or list of path for point cloud data
              pc_chunk_size:int=None, # output point chunk size
              n_pc_chunk:int=None, # output number of chunk
              hd_chunk_size:tuple|list=None, # output high dimension chunk size, tuple or list of tuple, same as input raster data by default
):
    '''Convert raster data to point cloud data'''
    logger = logging.getLogger(__name__)

    idx_zarr = zarr.open(idx,mode='r')
    logger.zarr_info(idx,idx_zarr)
    assert idx_zarr.ndim == 2, "idx dimentation is not 2."
    pc_chunk_size = get_pc_chunk_size_from_pc_chunk_size('idx','pc',
                                                         idx_zarr.chunks[1],idx_zarr.shape[1],
                                                         pc_chunk_size=pc_chunk_size,n_pc_chunk=n_pc_chunk)

    logger.info('loading idx into memory.')
    idx = zarr.open(idx,mode='r')[:]
    n_pc = idx.shape[1]

    if isinstance(ras,str):
        assert isinstance(pc,str)
        ras_list = [ras]; pc_list = [pc]
        if hd_chunk_size is not None:
            assert isinstance(hd_chunk_size,tuple)
            hd_chunk_size_list = [hd_chunk_size]
        else:
            hd_chunk_size_list = [None]
    else:
        assert isinstance(ras,list); assert isinstance(pc,list)
        ras_list = ras; pc_list = pc
        n_data = len(ras_list)
        if hd_chunk_size is not None:
            assert isinstance(hd_chunk_size,list)
            hd_chunk_size_list = hd_chunk_size
        else:
            hd_chunk_size_list = [None]*n_data

    logger.info('starting dask local cluster.')
    with LocalCluster() as cluster, Client(cluster) as client:
        logger.info('dask local cluster started.')

        _pc_list = ()
        for ras_path, pc_path, hd_chunk_size in zip(ras_list,pc_list,hd_chunk_size_list):
            logger.info(f'start to slice on {ras_path}')
            ras_zarr = zarr.open(ras_path,'r'); logger.zarr_info(ras_path, ras_zarr)
            if hd_chunk_size is None:
                logger.info(f'hd_chunk_size not setted. Use the one from {ras_path}.')
                hd_chunk_size = ras_zarr.chunks[2:]
            logger.info(f'hd_chunk_size: {hd_chunk_size}.')

            ras = da.from_zarr(ras_path,chunks=(*ras_zarr.chunks[:2],*hd_chunk_size)); logger.darr_info('ras',ras)

            with dask.config.set(**{'array.slicing.split_large_chunks': False}):
                pc = ras.reshape(-1,*ras.shape[2:])[np.ravel_multi_index((idx[0],idx[1]),dims=ras.shape[:2])]

            logger.darr_info('pc', pc)
            logger.info('rechunk pc data:')
            pc = pc.rechunk((pc_chunk_size,*pc.chunksize[1:]))
            logger.darr_info('pc', pc)
            _pc = pc.to_zarr(pc_path,overwrite=True,compute=False)
            logger.info(f'saving to {pc_path}.')
            _pc_list += (_pc,)

        logger.info('computing graph setted. doing all the computing.')
        futures = client.persist(_pc_list)
        progress(futures,notebook=False)
        da.compute(futures)
        logger.info('computing finished.')

    logger.info('dask cluster closed.')

# %% ../../nbs/CLI/pc.ipynb 8
@call_parse
def console_de_ras2pc(idx:str, # point cloud index
                      ras:Param(type=str,required=True,nargs='+',help='one or more path for raster data')=None,
                      pc:Param(type=str,required=True,nargs='+',help='output, one or more path for point cloud data')=None,
                      pc_chunk_size:int=None, # output point chunk size, same as input idx by default
                      n_pc_chunk:int=None, # output number of chunk
                      hd_chunk_size:Param(type=str,nargs='+',help='''output high dimension chunk size,
                      each size should be wrapped in quotation marks and size in each dimension are seperated with ",",
                      same as input raster data by default''')=None,
):
    '''Convert raster data to point cloud data'''
    if hd_chunk_size is not None:
        hd_chunk_size_ = []
        for size in hd_chunk_size:
            if len(size) == 0:
                size = ()
            else:
                size = size.split(',')
                size = tuple([int(i) for i in size])
            hd_chunk_size_.append(size)
    else:
        hd_chunk_size_ = None

    if len(ras)==1:
        ras = ras[0]
        pc = pc[0]
        if hd_chunk_size_ is not None:
            hd_chunk_size_ = hd_chunk_size_[0]

    de_ras2pc(idx,ras,pc,pc_chunk_size=pc_chunk_size,n_pc_chunk=n_pc_chunk,hd_chunk_size=hd_chunk_size_)

# %% ../../nbs/CLI/pc.ipynb 13
@log_args
@de_logger
def de_pc2ras(idx:str, # point cloud index
              pc:str|list, # path (in string) or list of path for point cloud data
              ras:str|list, # output, path (in string) or list of path for raster data
              shape:tuple, # shape of one image (nlines,width)
              az_chunk_size:int=None, # output azimuth chunk size, 
              n_az_chunk:int=None, # # output number of azimuth chunks
              r_chunk_size:int=None, # output range chunk size
              n_r_chunk:int=None, # output number of range chunks
):
    '''Convert point cloud data to raster data, filled with nan'''
    logger = logging.getLogger(__name__)

    idx_zarr = zarr.open(idx,mode='r')
    logger.zarr_info('idx', idx_zarr)
    assert idx_zarr.ndim == 2, "idx dimentation is not 2."
    chunk_size = get_ras_chunk_size_from_n_pc_chunk('idx','ras',
                                                    idx_zarr.shape[1],idx_zarr.chunks[1],
                                                    *shape,
                                                    az_chunk_size=az_chunk_size,n_az_chunk=n_az_chunk,
                                                    r_chunk_size=r_chunk_size,n_r_chunk=n_r_chunk
                                                    )
    logger.info('loading idx into memory.')
    idx = zarr.open(idx,mode='r')[:]
    n_pc = idx.shape[1]
    
    if isinstance(pc,str):
        assert isinstance(ras,str)
        pc_list = [pc]; ras_list = [ras]
    else:
        assert isinstance(pc,list); assert isinstance(ras,list)
        pc_list = pc; ras_list = ras

    logger.info('starting dask local cluster.')
    with LocalCluster() as cluster, Client(cluster) as client:
        logger.info('dask local cluster started.')

        _ras_list = ()

        for ras_path, pc_path in zip(ras_list,pc_list):
            logger.info(f'start to work on {pc_path}')
            pc_zarr = zarr.open(pc_path,'r')
            logger.zarr_info(pc_path,pc_zarr)

            pc = da.from_zarr(pc_path)
            logger.darr_info('pc', pc)
            ras = da.empty((shape[0]*shape[1],*pc.shape[1:]),chunks = (chunk_size[0]*shape[1],*pc_zarr.chunks[1:]), dtype=pc.dtype)
            ras[:] = np.nan
            ras[np.ravel_multi_index((idx[0],idx[1]),dims=shape)] = pc
            ras = ras.reshape(*shape,*pc.shape[1:])
            ras.rechunk((*chunk_size,*pc_zarr.chunks[1:]))
            logger.info('create ras dask array')
            logger.darr_info('ras', ras)
            _ras = ras.to_zarr(ras_path,overwrite=True,compute=False)
            _ras_list += (_ras,)

        logger.info('computing graph setted. doing all the computing.')
        futures = client.persist(_ras_list)
        progress(futures,notebook=False)
        da.compute(futures)
        logger.info('computing finished.')

    logger.info('dask cluster closed.')

# %% ../../nbs/CLI/pc.ipynb 17
@call_parse
@log_args
@de_logger
def de_pc_union(idx1:str, # index of the first point cloud
                idx2:str, # index of the second point cloud
                idx:str, # output, index of the union point cloud
                pc1:str|list=None, # path (in string) or list of path for the first point cloud data
                pc2:str|list=None, # path (in string) or list of path for the second point cloud data
                pc:str|list=None, #output, path (in string) or list of path for the union point cloud data
                pc_chunk_size:int=None, # chunk size in output data,optional
                n_pc_chunk:int=None, # number of chunk in output data, optional
):
    '''Get the union of two point cloud dataset.
    For points at their intersection, pc_data1 rather than pc_data2 is copied to the result pc_data.
    `pc_chunk_size` and `n_pc_chunk` are used to determine the final pc_chunk_size.
    If non of them are provided, the pc_chunk_size is setted as it in idx1.
    '''
    logger = logging.getLogger(__name__)

    idx1_zarr = zarr.open(idx1,mode='r'); logger.zarr_info(idx1,idx1_zarr)
    idx2_zarr = zarr.open(idx2,mode='r'); logger.zarr_info(idx2,idx2_zarr)
    logger.info('loading idx1 and idx2 into memory.')
    idx1 = idx1_zarr[:]; idx2 = idx2_zarr[:]

    logger.info('calculate the union')
    idx_path = idx
    idx, inv_iidx1, inv_iidx2, iidx2 = pc_union(idx1,idx2)
    n_pc = idx.shape[1]
    logger.info(f'number of points in the union: {idx.shape[1]}')
    pc_chunk_size = get_pc_chunk_size_from_pc_chunk_size('idx1','idx',
                                                         idx1_zarr.chunks[1],
                                                         n_pc,
                                                         pc_chunk_size=pc_chunk_size,n_pc_chunk=n_pc_chunk)
    
    idx_zarr = zarr.open(idx_path,'w',shape=idx.shape,dtype=idx.dtype,chunks=(2,pc_chunk_size))
    logger.info('write union idx')
    idx_zarr[:] = idx
    logger.info('write done')
    logger.zarr_info(idx_path, idx_zarr)
    
    if pc1 is None:
        logger.info('no point cloud data provided, exit.')
        return None

    if isinstance(pc1,str):
        assert isinstance(pc2,str); assert isinstance(pc,str)
        pc1_list = [pc1]; pc2_list = [pc2]; pc_list = [pc]
    else:
        assert isinstance(pc1,list); assert isinstance(pc2,list); assert isinstance(pc,list)
        pc1_list = pc1; pc2_list = pc2; pc_list = pc

    logger.info('starting dask local cluster.')
    with LocalCluster() as cluster, Client(cluster) as client:
        logger.info('dask local cluster started.')

        _pc_list = ()
        for pc1_path, pc2_path, pc_path in zip(pc1_list,pc2_list,pc_list):
            pc1_zarr = zarr.open(pc1_path,'r'); pc2_zarr = zarr.open(pc2_path,'r')
            logger.zarr_info(pc1_path, pc1_zarr); logger.zarr_info(pc2_path, pc2_zarr);
            pc1 = da.from_zarr(pc1_path); pc2 = da.from_zarr(pc2_path)
            logger.darr_info('pc1', pc1); logger.darr_info('pc2',pc2)
            logger.info('set up union pc data dask array.')
            pc = da.empty((n_pc,*pc1.shape[1:]),chunks = (pc_chunk_size,*pc1.chunks[1:]), dtype=pc1.dtype)
            logger.darr_info('pc',pc)
            pc[inv_iidx1] = pc1
            pc[inv_iidx2] = pc2[iidx2]
            _pc = pc.to_zarr(pc_path, overwrite=True,compute=False)
            _pc_list += (_pc,)

        logger.info('computing graph setted. doing all the computing.')
        futures = client.persist(_pc_list)
        progress(futures,notebook=False)
        da.compute(futures)
        logger.info('computing finished.')

    logger.info('dask cluster closed.')

# %% ../../nbs/CLI/pc.ipynb 21
@call_parse
@log_args
@de_logger
def de_pc_intersect(idx1:str, # index of the first point cloud
                    idx2:str, # index of the second point cloud
                    idx:str, # output, index of the union point cloud
                    pc1:str|list=None, # path (in string) or list of path for the first point cloud data
                    pc2:str|list=None, # path (in string) or list of path for the second point cloud data
                    pc:str|list=None, #output, path (in string) or list of path for the union point cloud data
                    pc_chunk_size:int=None, # chunk size in output data,optional
                    n_pc_chunk:int=None, # number of chunk in output data, optional
                    prefer_1=True, # save pc1 on intersection to output pc dataset by default `True`. Otherwise, save data from pc2
):
    '''Get the intersection of two point cloud dataset.
    `pc_chunk_size` and `n_pc_chunk` are used to determine the final pc_chunk_size.
    If non of them are provided, the n_pc_chunk is set to n_chunk in idx1.
    '''
    logger = logging.getLogger(__name__)

    idx1_zarr = zarr.open(idx1,mode='r'); logger.zarr_info(idx1,idx1_zarr)
    idx2_zarr = zarr.open(idx2,mode='r'); logger.zarr_info(idx2,idx2_zarr)
    logger.info('loading idx1 and idx2 into memory.')
    idx1 = idx1_zarr[:]; idx2 = idx2_zarr[:]

    logger.info('calculate the intersection')
    idx_path = idx
    idx, iidx1, iidx2 = pc_intersect(idx1,idx2)
    n_pc = idx.shape[1]
    logger.info(f'number of points in the intersection: {idx.shape[1]}')
    pc_chunk_size = get_pc_chunk_size_from_n_pc_chunk('idx1','idx',idx1_zarr.shape[1],idx1_zarr.chunks[1],n_pc,pc_chunk_size=pc_chunk_size,n_pc_chunk=n_pc_chunk)
    
    idx_zarr = zarr.open(idx_path,'w',shape=idx.shape,dtype=idx.dtype,chunks=(2,pc_chunk_size))
    logger.info('write intersect idx')
    idx_zarr[:] = idx
    logger.info('write done')
    logger.zarr_info(idx_path, idx_zarr)

    if (pc1 is None) and (pc2 is None):
        logger.info('no point cloud data provided, exit.')
        return None

    if prefer_1:
        logger.info('select pc1 as pc_input.')
        iidx = iidx1; pc_input = pc1
    else:
        logger.info('select pc2 as pc_input.')
        iidx = iidx2; pc_input = pc2

    if isinstance(pc_input,str):
        assert isinstance(pc,str)
        pc_input_list = [pc_input]; pc_list = [pc]
    else:
        assert isinstance(pc_input,list); assert isinstance(pc,list)
        pc_input_list = pc_input; pc_list = pc

    logger.info('starting dask local cluster.')
    with LocalCluster() as cluster, Client(cluster) as client:
        logger.info('dask local cluster started.')

        _pc_list = ()
        for pc_input_path, pc_path in zip(pc_input_list,pc_list):
            pc_input_zarr = zarr.open(pc_input_path,'r')
            logger.zarr_info(pc_input_path,pc_input_zarr)
            pc_input = da.from_zarr(pc_input_path)
            logger.darr_info('pc_input', pc_input)

            logger.info('set up intersect pc data dask array.')
            pc = da.empty((n_pc,*pc_input.shape[1:]),chunks = (pc_chunk_size,*pc_input.chunks[1:]), dtype=pc_input.dtype)
            logger.darr_info('pc',pc)
            pc[:] = pc_input[iidx]
            _pc = pc.to_zarr(pc_path, overwrite=True,compute=False)
            _pc_list += (_pc,)

        logger.info('computing graph setted. doing all the computing.')
        futures = client.persist(_pc_list)
        progress(futures,notebook=False)
        da.compute(futures)
        logger.info('computing finished.')
    logger.info('dask cluster closed.')

# %% ../../nbs/CLI/pc.ipynb 25
@call_parse
@log_args
@de_logger
def de_pc_diff(idx1:str, # index of the first point cloud
               idx2:str, # index of the second point cloud
               idx:str, # output, index of the union point cloud
               pc1:str|list=None, # path (in string) or list of path for the first point cloud data
               pc:str|list=None, #output, path (in string) or list of path for the union point cloud data
               pc_chunk_size:int=None, # chunk size in output data,optional
               n_pc_chunk:int=None, # number of chunk in output data, optional
              ):
    '''Get the point cloud in `idx1` that are not in `idx2`.
    `pc_chunk_size` and `n_pc_chunk` are used to determine the final pc_chunk_size.
    If non of them are provided, the n_pc_chunk is set to n_chunk in idx1.
    '''
    logger = logging.getLogger(__name__)

    idx1_zarr = zarr.open(idx1,mode='r'); logger.zarr_info(idx1,idx1_zarr)
    idx2_zarr = zarr.open(idx2,mode='r'); logger.zarr_info(idx2,idx2_zarr)
    logger.info('loading idx1 and idx2 into memory.')
    idx1 = idx1_zarr[:]; idx2 = idx2_zarr[:]

    logger.info('calculate the diff.')
    idx_path = idx
    idx, iidx1 = pc_diff(idx1,idx2)
    n_pc = idx.shape[1]
    logger.info(f'number of points in the diff: {idx.shape[1]}')
    pc_chunk_size = get_pc_chunk_size_from_n_pc_chunk('idx1','idx',idx1_zarr.shape[1],idx1_zarr.chunks[1],n_pc,pc_chunk_size=pc_chunk_size,n_pc_chunk=n_pc_chunk)
    
    idx_zarr = zarr.open(idx_path,'w',shape=idx.shape,dtype=idx.dtype,chunks=(2,pc_chunk_size))
    logger.info('write intersect idx')
    idx_zarr[:] = idx
    logger.info('write done')
    logger.zarr_info(idx_path, idx_zarr)

    if pc1 is None:
        logger.info('no point cloud data provided, exit.')
        return None

    if isinstance(pc1,str):
        assert isinstance(pc,str)
        pc1_list = [pc1]; pc_list = [pc]
    else:
        assert isinstance(pc1,list); assert isinstance(pc,list)
        pc1_list = pc1; pc_list = pc

    logger.info('starting dask local cluster.')
    with LocalCluster() as cluster, Client(cluster) as client:
        logger.info('dask local cluster started.')

        _pc_list = ()
        for pc1_path, pc_path in zip(pc1_list,pc_list):
            pc1_zarr = zarr.open(pc1_path,'r'); logger.zarr_info(pc1_path, pc1_zarr)
            pc1 = da.from_zarr(pc1_path); logger.darr_info('pc1', pc1)
            logger.info('set up diff pc data dask array.')
            pc = da.empty((n_pc,*pc1.shape[1:]),chunks = (pc_chunk_size,*pc1.chunks[1:]), dtype=pc1.dtype)
            logger.darr_info('pc',pc)
            pc[:] = pc1[iidx1]
            _pc = pc.to_zarr(pc_path, overwrite=True,compute=False)
            _pc_list += (_pc,)

        logger.info('computing graph setted. doing all the computing.')
        futures = client.persist(_pc_list)
        progress(futures,notebook=False)
        da.compute(futures)
        logger.info('computing finished.')
    logger.info('dask cluster closed.')

# %% ../../nbs/CLI/pc.ipynb 29
@call_parse
@log_args
@de_logger
def de_pc_logic_ras(ras, # the raster image used for thresholding
                    idx, # output, index of selected pixels
                    operation:str, # logical operation on input ras
                    pc_chunk_size:int=None, # chunk size in output data,optional
                    n_pc_chunk:int=None, # number of chunk in output data, optional
                   ):
    '''generate point cloud index based on logical operation of one raster image.
    '''
    idx_path = idx
    logger = logging.getLogger(__name__)
    ras_zarr = zarr.open(ras, mode='r'); logger.zarr_info(ras,ras_zarr)

    ras = ras_zarr[:]; logger.info('loading ras into memory.')
    is_pc = ne.evaluate(operation,{'ras':ras})
    logger.info(f'select pc based on operation: {operation}')
    idx = np.stack(np.where(is_pc)).astype(np.int32)
    n_pc = idx.shape[1]
    logger.info(f'number of selected pixels: {n_pc}.')
    pc_chunk_size = get_pc_chunk_size_from_n_ras_chunk('ras','idx',
                                                       *ras_zarr.shape[:2],
                                                       *ras_zarr.chunks[:2],
                                                       n_pc,pc_chunk_size=pc_chunk_size,n_pc_chunk=n_pc_chunk)
    idx_zarr = zarr.open(idx_path,'w',dtype=idx.dtype,shape=idx.shape,chunks=(2,pc_chunk_size))
    logger.info('writing idx.')
    idx_zarr[:] = idx
    logger.info('write done.')

# %% ../../nbs/CLI/pc.ipynb 32
@call_parse
@log_args
@de_logger
def de_pc_logic_pc(idx_in:str,# the index of input pc data
                   pc_in:str, # the point cloud data used for thresholding
                   idx:str, # output, index of selected pixels
                   operation:str, # operator
                   pc_chunk_size:int=None, # chunk size in output data,optional
                   n_pc_chunk:int=None, # number of chunk in output data, optional
                   ):
    '''generate point cloud index and data based on logical operation one point cloud data.
    '''
    idx_path = idx
    logger = logging.getLogger(__name__)
    idx_in_zarr = zarr.open(idx_in,mode='r'); logger.zarr_info(idx_in,idx_in_zarr)
    pc_in_zarr = zarr.open(pc_in, mode='r'); logger.zarr_info(pc_in,pc_in_zarr)

    idx_in = idx_in_zarr[:]; logger.info('loading idx_in into memory.')
    pc_in = pc_in_zarr[:]; logger.info('loading pc_in into memory.')

    is_pc = ne.evaluate(operation,{'pc_in':pc_in})
    logger.info(f'select pc based on operation: {operation}')
    idx = idx_in[:,is_pc]
    n_pc = idx.shape[1]
    logger.info(f'number of selected pixels: {n_pc}.')
    pc_chunk_size = get_pc_chunk_size_from_n_pc_chunk('idx_in','idx',idx_in_zarr.shape[1],idx_in_zarr.chunks[1],n_pc, pc_chunk_size=pc_chunk_size, n_pc_chunk= n_pc_chunk)
    idx_zarr = zarr.open(idx_path,'w',dtype=idx.dtype,shape=idx.shape,chunks=(2,pc_chunk_size))
    logger.zarr_info('idx', idx_zarr)
    logger.info('writing idx.')
    idx_zarr[:] = idx
    logger.info('write done.')

# %% ../../nbs/CLI/pc.ipynb 36
@call_parse
@log_args
@de_logger
def de_pc_select_data(idx_in:str, # index of the input data
                      idx:str, # index of the output data
                      pc_in:str|list, # path (in string) or list of path for the input point cloud data
                      pc:str|list, # output, path (in string) or list of path for the output point cloud data
                      pc_chunk_size:int=None, # chunk size in output data,optional
                      n_pc_chunk:int=None, # number of chunk in output data, optional
                     ):
    '''generate point cloud data based on its index and one point cloud data.
    The index of generated point cloud data must in the index of the old one.
    '''
    idx_in_path = idx_in; idx_path = idx
    logger = logging.getLogger(__name__)
    idx_in_zarr = zarr.open(idx_in_path,mode='r'); logger.zarr_info(idx_in_path,idx_in_zarr)
    idx_zarr = zarr.open(idx_path,mode='r'); logger.zarr_info(idx_path,idx_zarr)
    logger.info('loading idx_in and idx into memory.')
    idx_in = idx_in_zarr[:]; idx = idx_zarr[:]
    iidx_in, iidx = pc_intersect(idx_in,idx)[1:]
    np.testing.assert_array_equal(iidx,np.arange(iidx.shape[0]),err_msg='idx have points that are not covered by idx_in.')
    n_pc = iidx_in.shape[0]
    pc_chunk_size = get_pc_chunk_size_from_pc_chunk_size('idx','pc',idx_zarr.chunks[1],n_pc,pc_chunk_size=pc_chunk_size,n_pc_chunk=n_pc_chunk)

    if isinstance(pc_in,str):
        assert isinstance(pc,str)
        pc_in_list = [pc_in]; pc_list = [pc]
    else:
        assert isinstance(pc_in,list); assert isinstance(pc,list)
        pc_in_list = pc_in; pc_list = pc

    logger.info('starting dask local cluster.')
    with LocalCluster() as cluster, Client(cluster) as client:
        logger.info('dask local cluster started.')

        _pc_list = ()
        for pc_in_path, pc_path in zip(pc_in_list,pc_list):
            pc_in_zarr = zarr.open(pc_in_path,'r'); logger.zarr_info(pc_in_path, pc_in_zarr)
            pc_in = da.from_zarr(pc_in_path); logger.darr_info('pc_in', pc_in)
            logger.info('set up selected pc data dask array.')
            pc = da.empty((n_pc,*pc_in.shape[1:]),chunks = (pc_chunk_size,*pc_in.chunks[1:]), dtype=pc_in.dtype)
            logger.darr_info('pc',pc)
            pc[:] = pc_in[iidx_in]
            _pc = pc.to_zarr(pc_path, overwrite=True,compute=False)
            _pc_list += (_pc,)

        logger.info('computing graph setted. doing all the computing.')
        futures = client.persist(_pc_list)
        progress(futures,notebook=False)
        da.compute(futures)
        logger.info('computing finished.')
    logger.info('dask cluster closed.')
