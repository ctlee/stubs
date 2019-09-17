""" Example docstring
stuff

"""


from collections import Counter
from collections import OrderedDict as odict
from collections import defaultdict as ddict
from termcolor import colored
import pandas as pd
import dolfin as d
import mpi4py.MPI as pyMPI
import petsc4py.PETSc as PETSc
Print = PETSc.Sys.Print

import sympy
from sympy.parsing.sympy_parser import parse_expr
from sympy import Heaviside, lambdify
from sympy.utilities.iterables import flatten

import numpy as np
from scipy.integrate import solve_ivp

import pint
from pprint import pprint
from tabulate import tabulate
from copy import copy, deepcopy

import stubs.common as common
import stubs
#import common
#import unit as ureg
#import data_manipulation
from stubs import unit as ureg
#import stubs.data_manipulation as data_manipulation
#import stubs.flux_assembly as flux_assembly

comm = d.MPI.comm_world
rank = comm.rank
size = comm.size
root = 0


# ====================================================
# ====================================================
# Base Classes
# ====================================================
# ====================================================
class _ObjectContainer(object):
    """
    This is a class
    """
    def __init__(self, ObjectClass, df=None, Dict=None):
        self.Dict = odict()
        self.dtypes = {}
        self.ObjectClass = ObjectClass
        self.propertyList = [] # properties to print
#        self.name_key = name_key
        if df is not None:
            self.add_pandas_dataframe(df)
        if Dict is not None:
            self.Dict = odict(Dict)
    def add_property(self, property_name, item):
        setattr(self, property_name, item)
    def add_property_to_all(self, property_name, item):
        for obj in self.Dict.values():
            setattr(obj, property_name, item)
    def add(self, item):
        self.Dict[item.name] = item
    def remove(self, name):
        self.Dict.pop(name)
    def add_pandas_dataframe(self, df):
        for _, row in df.iterrows():
            itemDict = row.to_dict()
            self.Dict[row.name] = self.ObjectClass(row.name, Dict=itemDict)
        self.dtypes.update(df.dtypes.to_dict())
#            name = itemDict[self.name_key]
#            itemDict.pop(self.name_key)
#            self.Dict[name] = self.ObjectClass(name, itemDict)
    def get_property(self, property_name):
        # returns a dict of properties
        property_dict = {}
        for key, obj in self.Dict.items():
            property_dict[key] = getattr(obj, property_name)
        return property_dict

    def where_equals(self, property_name, value):
        """
        Links objects from ObjectContainer2 to ObjectContainer1 (the _ObjectContainer invoking
        this method).

        Parameters
        ----------
        property_name : str
            Name of property to check values of
        value : variable type
            Value to check against

        Example Usage
        -------------
        CD.where_equals('compartment_name', 'cyto')

        Returns
        -------
        objectList: list
            List of objects from _ObjectContainer that matches the criterion
        """
        objList = []
        for key, obj in self.Dict.items():
            if getattr(obj, property_name) == value:
                objList.append(obj)
        return objList

        #TODO: instead of linked_name make a dictionary of linked objects
    def link_object(self, ObjectContainer2, property_name1, property_name2, linked_name, value_is_key=False):
        """
        Links objects from ObjectContainer2 to ObjectContainer1 (the _ObjectContainer invoking
        this method).

        Parameters
        ----------
        with_attribution : bool, Optional, default: True
            Set whether or not to display who the quote is from
        ObjectContainer2 : _ObjectContainer type
            _ObjectContainer with objects we are linking to
        property_name1 : str
            Name of property of object in ObjectContainer1 to match
        property_name2 : str
            Name of property of object in ObjectContainer2 to match
        linked_name : str
            Name of new property in ObjectContainer1 with linked object

        Example Usage
        -------------
        SD = {'key0': sd0, 'key1': sd1}; CD = {'key0': cd0, 'key1': cd1}
        sd0.compartment_name == 'cyto'
        cd0.name == 'cyto'
        >> SD.link_object(CD,'compartment_name','name','compartment')
        sd0.compartment == cd0

        Returns
        -------
        ObjectContainer1 : _ObjectContainer
            _ObjectContainer where each object has an added property linking to some
            object from ObjectContainer2
        """
        for _, obj1 in self.Dict.items():
            obj1_value = getattr(obj1, property_name1)
            # if type dict, then match values of entries with ObjectContainer2
            if type(obj1_value) == dict:
                newDict = odict()
                for key, value in obj1_value.items():
                    objList = ObjectContainer2.where_equals(property_name2, value)
                    if len(objList) != 1:
                        raise Exception('Either none or more than one objects match this condition')
                    if value_is_key:
                        newDict.update({value: objList[0]})
                    else:
                        newDict.update({key: objList[0]})

                setattr(obj1, linked_name, newDict)
            #elif type(obj1_value) == list or type(obj1_value) == set:
            #    newList = []
            #    for value in obj1_value:
            #        objList = ObjectContainer2.where_equals(property_name2, value)
            #        if len(objList) != 1:
            #            raise Exception('Either none or more than one objects match this condition')
            #        newList.append(objList[0])
            #    setattr(obj1, linked_name, newList)
            elif type(obj1_value) == list or type(obj1_value) == set:
                newDict = odict()
                for value in obj1_value:
                    objList = ObjectContainer2.where_equals(property_name2, value)
                    if len(objList) != 1:
                        raise Exception('Either none or more than one objects match this condition')
                    newDict.update({value: objList[0]})
                setattr(obj1, linked_name, newDict)
            # standard behavior
            else: 
                objList = ObjectContainer2.where_equals(property_name2, obj1_value)
                if len(objList) != 1:
                    raise Exception('Either none or more than one objects match this condition')
                setattr(obj1, linked_name, objList[0])

    def copy_linked_property(self, linked_name, linked_name_property, property_name):
        """
        Convenience function to copy a property from a linked object
        """
        for _, obj in self.Dict.items():
            linked_obj = getattr(obj, linked_name)
            setattr(obj, property_name, getattr(linked_obj, linked_name_property))


    def doToAll(self, method_name, kwargs=None):
        for name, instance in self.Dict.items():
            if kwargs is None:
                getattr(instance, method_name)()
            else:
                getattr(instance, method_name)(**kwargs)

    def get_pandas_dataframe(self, propertyList=[]):
        df = pd.DataFrame()
        if propertyList and 'idx' not in propertyList:
            propertyList.insert(0, 'idx')
        for idx, (name, instance) in enumerate(self.Dict.items()):
            df = df.append(instance.get_pandas_series(propertyList=propertyList, idx=idx))
        # sometimes types are recast. change entries into their original types
        for dtypeName, dtype in self.dtypes.items():
            if dtypeName in df.columns: 
                df = df.astype({dtypeName: dtype})

        return df
    def get_index(self, idx):
        """
        Get an element of the object container ordered dict by referencing its index
        """
        return list(self.Dict.values())[idx]

    def print(self, tablefmt='fancy_grid', propertyList=[]):
        if rank == root:
            if propertyList:
                if type(propertyList) != list: propertyList=[propertyList]
            elif hasattr(self, 'propertyList'):
                propertyList = self.propertyList
            df = self.get_pandas_dataframe(propertyList=propertyList)
            if propertyList:
                df = df[propertyList]
    
            print(tabulate(df, headers='keys', tablefmt=tablefmt))#,
                   #headers='keys', tablefmt=tablefmt), width=120)
        else: 
            pass

    def __str__(self):
        df = self.get_pandas_dataframe(propertyList=self.propertyList)
        df = df[self.propertyList]

        return tabulate(df, headers='keys', tablefmt='fancy_grid')
        #TODO: look this up
               #headers='keys', tablefmt=tablefmt), width=120)

    def vprint(self, keyList=None, propertyList=[], print_all=False):
        # in order of priority: kwarg, container object property, else print all keys
        if rank == root:
            if keyList:
                if type(keyList) != list: keyList=[keyList]
            elif hasattr(self, 'keyList'):
                keyList = self.keyList
            else:
                keyList = list(self.Dict.keys())

            if propertyList:
                if type(propertyList) != list: propertyList=[propertyList]
            elif hasattr(self, 'propertyList'):
                propertyList = self.propertyList

            if print_all: propertyList = []
            for key in keyList:
                self.Dict[key].print(propertyList=propertyList)
        else:
            pass


class _ObjectInstance(object):
    def __init__(self, name, Dict=None):
        self.name = name
        if Dict:
            self.fromDict(Dict)
    def fromDict(self, Dict):
        for key, item in Dict.items():
            setattr(self, key, item)
    def combineDicts(self, dict1=None, dict2=None, new_dict_name=None):
        setattr(self, new_dict_name, getattr(self,dict1).update(getattr(self,dict2)))
    def assemble_units(self, value_name=None, unit_name='unit', assembled_name=None):
        """
        Simply multiplies a value by a unit (pint type) to create a pint "Quantity" object 
        """
        if not assembled_name:
            assembled_name = unit_name

        value = 1 if not value_name else getattr(self, value_name)
        #value = getattr(self, value_name)
        unit = getattr(self, unit_name)
        if type(unit) == str:
            unit = ureg(unit)
        setattr(self, assembled_name, value*unit)

    def get_pandas_series(self, propertyList=[], idx=None):
        if propertyList:
            dict_to_convert = odict({'idx': idx})
            dict_to_convert.update(odict([(key,val) for (key,val) in self.__dict__.items() if key in propertyList]))
        else:
            dict_to_convert = self.__dict__
        return pd.Series(dict_to_convert, name=self.name)
    def print(self, propertyList=[]):
        if rank==root:
            print("Name: " + self.name)
            # if a custom list of properties to print is provided, only use those
            if propertyList:
                dict_to_print = dict([(key,val) for (key,val) in self.__dict__.items() if key in propertyList])
            else:
                dict_to_print = self.__dict__
            pprint(dict_to_print, width=240)
        else:
            pass


# ==============================================================================
# ==============================================================================
# Classes for parameters, species, compartments, reactions, and fluxes
# ==============================================================================
# ==============================================================================

# parameters, compartments, species, reactions, fluxes
class ParameterContainer(_ObjectContainer):
    def __init__(self, df=None, Dict=None):
        super().__init__(Parameter, df, Dict)
        self.propertyList = ['name', 'value', 'unit', 'is_time_dependent', 'symExpr', 'notes', 'group']

class Parameter(_ObjectInstance):
    def __init__(self, name, Dict=None):
        super().__init__(name, Dict)
    def assembleTimeDependentParameters(self): 
        if self.is_time_dependent:
            self.symExpr = parse_expr(self.symExpr)
            if rank==root: print("Creating dolfin object for time-dependent parameter %s" % self.name)
            self.dolfinConstant = d.Constant(self.value)


class SpeciesContainer(_ObjectContainer):
    def __init__(self, df=None, Dict=None):
        super().__init__(Species, df, Dict)
        self.propertyList = ['name', 'compartment_name', 'compartment_index', 'concentration_units', 'D', 'initial_condition', 'group']

    def assemble_compartment_indices(self, RD, CD, settings):
        """
        Adds a column to the species dataframe which indicates the index of a species relative to its compartment
        """
        num_species_per_compartment = RD.get_species_compartment_counts(self, CD, settings)
        for compartment, num_species in num_species_per_compartment.items():
            idx = 0
            comp_species = [sp for sp in self.Dict.values() if sp.compartment_name==compartment]
            for sp in comp_species:
                if sp.is_in_a_reaction or sp.parent_species:
                    sp.compartment_index = idx
                    idx += 1
                else:
                    print('Warning: species %s is not used in any reactions!' % sp.name)


    def assemble_dolfin_functions(self, RD, CD, settings):
        """
        define dof/solution vectors (dolfin trialfunction, testfunction, and function types) based on number of species appearing in reactions
        IMPORTANT: this function will create additional species on boundaries in order to use operator-splitting later on
        e.g.
        A [cyto] + B [pm] <-> C [pm]
        Since the value of A is needed on the pm there will be a species A_b_pm which is just the values of A on the boundary pm
        """

        # functions to run beforehand as we need their results
        num_species_per_compartment = RD.get_species_compartment_counts(self, CD, settings)
        CD.get_min_max_dim()
        self.assemble_compartment_indices(RD, CD, settings)
        CD.add_property_to_all('is_in_a_reaction', False)
        CD.add_property_to_all('V', None)

        V, u, v = {}, {}, {}
        for compartment_name, num_species in num_species_per_compartment.items():
            compartmentDim = CD.Dict[compartment_name].dimensionality
            CD.Dict[compartment_name].num_species = num_species
            if rank==root:
                print('Compartment %s (dimension: %d) has %d species associated with it' %
                      (compartment_name, compartmentDim, num_species))
        
            # u is the actual function. t is for linearized versions. k is for picard iterations. n is for last time-step solution
            if num_species == 1:
                V[compartment_name] = d.FunctionSpace(CD.meshes[compartment_name], 'P', 1)
                u[compartment_name] = {'u': d.Function(V[compartment_name]), 't': d.TrialFunction(V[compartment_name]),
                'k': d.Function(V[compartment_name]), 'n': d.Function(V[compartment_name])}
                v[compartment_name] = d.TestFunction(V[compartment_name])
            else: # vector space
                V[compartment_name] = d.VectorFunctionSpace(CD.meshes[compartment_name], 'P', 1, dim=num_species)
                u[compartment_name] = {'u': d.Function(V[compartment_name]), 't': d.TrialFunctions(V[compartment_name]),
                'k': d.Function(V[compartment_name]), 'n': d.Function(V[compartment_name])}
                v[compartment_name] = d.TestFunctions(V[compartment_name])

        if not settings['add_boundary_species']: # if the setting is true sub_species will be added 
            # now we create boundary functions, which are defined on the function spaces of the surrounding mesh
            V['boundary'] = {}
            for compartment_name, num_species in num_species_per_compartment.items():
                compartmentDim = CD.Dict[compartment_name].dimensionality
                if compartmentDim == CD.max_dim: # mesh may have boundaries
                    V['boundary'][compartment_name] = {}
                    for boundary_name, boundary_mesh in CD.meshes.items():
                        if compartment_name != boundary_name:
                            if num_species == 1:
                                boundaryV = d.FunctionSpace(CD.meshes[boundary_name], 'P', 1)
                            else:
                                boundaryV = d.VectorFunctionSpace(CD.meshes[boundary_name], 'P', 1, dim=num_species)
                            V['boundary'][compartment_name].update({boundary_name: boundaryV})
                            u[compartment_name]['b'+boundary_name] = d.Function(boundaryV)

        # associate indexed functions with dataframe
        for key, sp in self.Dict.items():
            sp.u = {}
            sp.v = None
            if sp.is_in_a_reaction:
                sp.compartment.is_in_a_reaction = True
                num_species = sp.compartment.num_species
                for key in u[sp.compartment_name].keys():
                    if num_species == 1:
                        sp.u.update({key: u[sp.compartment_name][key]})
                        sp.v = v[sp.compartment_name]
                    else:
                        sp.u.update({key: u[sp.compartment_name][key][sp.compartment_index]})
                        sp.v = v[sp.compartment_name][sp.compartment_index]

        # # associate function spaces with dataframe
        for key, comp in CD.Dict.items():
            if comp.is_in_a_reaction:
                comp.V = V[comp.name]

        self.u = u
        self.v = v
        self.V = V

    def assign_initial_conditions(self):
        keys = ['k', 'n', 'u']
        for sp in self.Dict.values():
            comp_name = sp.compartment_name
            for key in keys:
                # stubs.data_manipulation.dolfinSetFunctionValues(self.u[comp_name][key], sp.initial_condition,
                #                                           self.V[comp_name], sp.compartment_index)
                stubs.data_manipulation.dolfinSetFunctionValues(self.u[comp_name][key], sp.initial_condition,
                                                                sp.compartment_index)
            #self.u[comp_name]['u'].assign(self.u[comp_name]['n'])
            if rank==root: print("Assigned initial condition for species %s" % sp.name)

        # add boundary values
        for comp_name in self.u.keys():
            for ukey in self.u[comp_name].keys():
                if 'b' in key[0]:
                    self.u[comp_name][ukey].interpolate(self.u[comp_name]['u'])




class Species(_ObjectInstance):
    def __init__(self, name, Dict=None):
        super().__init__(name, Dict)
        self.sub_species = {} # additional compartments this species may live in in addition to its primary one
        self.is_in_a_reaction = False
        self.is_an_added_species = False
        self.parent_species = None
        self.dof_map = {}


class CompartmentContainer(_ObjectContainer):
    def __init__(self, df=None, Dict=None):
        super().__init__(Compartment, df, Dict)
        self.propertyList = ['name', 'dimensionality', 'num_species', 'num_vertices', 'cell_marker', 'is_in_a_reaction', 'nvolume']
        self.meshes = {}
        self.vertex_mappings = {} # from submesh -> parent indices
    def load_mesh(self, mesh_key, mesh_str):
        self.meshes[mesh_key] = d.Mesh(mesh_str)
    def extract_submeshes(self, main_mesh_str, save_to_file):
        main_mesh = self.Dict[main_mesh_str]
        surfaceDim = main_mesh.dimensionality - 1

        self.Dict[main_mesh_str].mesh = self.meshes[main_mesh_str]

        vmesh = self.meshes[main_mesh_str]
        bmesh = d.BoundaryMesh(vmesh, "exterior")

        # Very odd behavior - when bmesh.entity_map() is called together with .array() it will return garbage values. We
        # should only call entity_map once to avoid this
        emap_0 = bmesh.entity_map(0)
        bmesh_emap_0 = deepcopy(emap_0.array())
        emap_2 = bmesh.entity_map(2)
        bmesh_emap_2 = deepcopy(emap_2.array())
        vmf = d.MeshFunction("size_t", vmesh, surfaceDim, vmesh.domains())
        bmf = d.MeshFunction("size_t", bmesh, surfaceDim)
        for idx, facet in enumerate(d.entities(bmesh,surfaceDim)): # iterate through faces of bmesh
            #vmesh_idx = bmesh.entity_map(surfaceDim)[idx] # get the index of the face on vmesh corresponding to this face on bmesh
            vmesh_idx = bmesh_emap_2[idx] # get the index of the face on vmesh corresponding to this face on bmesh
            vmesh_boundarynumber = vmf.array()[vmesh_idx] # get the value of the mesh function at this face
            bmf.array()[idx] = vmesh_boundarynumber # set the value of the boundary mesh function to be the same value


        for key, obj in self.Dict.items():
            if key!=main_mesh_str and obj.dimensionality==surfaceDim:
                # TODO: fix this
                if size > 1:
                    print("CPU %d: Loading submesh for %s from file" % (rank, key))
                    submesh = d.Mesh(d.MPI.comm_self, 'submeshes/submesh_' + obj.name + '_' + str(obj.cell_marker) + '.xml')
                    self.meshes[key] = submesh
                    obj.mesh = submesh
                else:
                    submesh = d.SubMesh(bmesh, bmf, obj.cell_marker)                
                    self.vertex_mappings[key] = submesh.data().array("parent_vertex_indices", 0)
                    self.meshes[key] = submesh
                    obj.mesh = submesh
                    if save_to_file:
                        save_str = 'submeshes/submesh_' + obj.name + '_' + str(obj.cell_marker) + '.xml'
                        d.File(save_str) << submesh
            # integration measures
            if obj.dimensionality==main_mesh.dimensionality:
                obj.ds = d.Measure('ds', domain=obj.mesh, subdomain_data=vmf, metadata={'quadrature_degree': 3})
                obj.dP = None
            elif obj.dimensionality<main_mesh.dimensionality:
                obj.dP = d.Measure('dP', domain=obj.mesh)
                obj.ds = None
            else:
                raise Exception("main_mesh is not a maximum dimension compartment")
            obj.dx = d.Measure('dx', domain=obj.mesh, metadata={'quadrature_degree': 3})

        # Get # of vertices
        for key, mesh in self.meshes.items():        
            num_vertices = mesh.num_vertices()
            print('CPU %d: My partition of mesh %s has %d vertices' % (rank, key, num_vertices))
            self.Dict[key].num_vertices = num_vertices

        self.vmf = vmf
        self.bmesh = bmesh
        self.bmesh_emap_0 = bmesh_emap_0
        self.bmesh_emap_2 = bmesh_emap_2
        self.bmf = bmf



    def compute_scaling_factors(self):
        self.doToAll('compute_nvolume')
        for key, obj in self.Dict.items():
            obj.scale_to = {}
            for key2, obj2 in self.Dict.items():
                if key != key2:
                    obj.scale_to.update({key2: obj.nvolume / obj2.nvolume})
    def get_min_max_dim(self):
        comp_dims = [comp.dimensionality for comp in self.Dict.values()]
        self.min_dim = min(comp_dims)
        self.max_dim = max(comp_dims)



class Compartment(_ObjectInstance):
    def __init__(self, name, Dict=None):
        super().__init__(name, Dict)
    def compute_nvolume(self):
        self.nvolume = d.assemble(d.Constant(1.0)*self.dx) * self.compartment_units ** self.dimensionality



class ReactionContainer(_ObjectContainer):
    def __init__(self, df=None, Dict=None):
        super().__init__(Reaction, df, Dict)
        #self.propertyList = ['name', 'LHS', 'RHS', 'eqn_f', 'eqn_r', 'paramDict', 'reaction_type', 'explicit_restriction_to_domain', 'group']
        self.propertyList = ['name', 'LHS', 'RHS', 'eqn_f', 'eqn_r']

    def get_species_compartment_counts(self, SD, CD, settings):
        self.doToAll('get_involved_species_and_compartments', {"SD": SD, "CD": CD})
        all_involved_species = set([sp for species_set in [rxn.involved_species_link.values() for rxn in self.Dict.values()] for sp in species_set])
        for sp_name, sp in SD.Dict.items():
            if sp in all_involved_species:
                sp.is_in_a_reaction = True

        compartment_counts = [sp.compartment_name for sp in all_involved_species]


        if settings['add_boundary_species']:
            ### additional boundary functions
            # get volumetric species which should also be defined on their boundaries
            sub_species_to_add = []
            for rxn in self.Dict.values():
                involved_compartments = [CD.Dict[comp_name] for comp_name in rxn.involved_compartments]
                rxn_min_dim = min([comp.dimensionality for comp in involved_compartments])
                rxn_max_dim = min([comp.dimensionality for comp in involved_compartments])
                for sp_name in rxn.involved_species:
                    sp = SD.Dict[sp_name]
                    if sp.dimensionality > rxn_min_dim: # species is involved in a boundary reaction
                        for comp in involved_compartments:
                            if comp.name != sp.compartment_name:
                                sub_species_to_add.append((sp_name, comp.name))
                                #sp.sub_species.update({comp.name: None})

            # Create a new species on boundaries
            sub_sp_list = []
            for sp_name, comp_name in set(sub_species_to_add):
                sub_sp_name = sp_name+'_sub_'+comp_name
                compartment_counts.append(comp_name)
                if sub_sp_name not in SD.Dict.keys():
                    if rank==root:
                        print((colored('\nSpecies %s will have a new function defined on compartment %s with name: %s\n'
                            % (sp_name, comp_name, sub_sp_name))))

                    sub_sp = copy(SD.Dict[sp_name])
                    sub_sp.is_an_added_species = True
                    sub_sp.name = sub_sp_name
                    sub_sp.compartment_name = comp_name
                    sub_sp.compartment = CD.Dict[comp_name]
                    sub_sp.is_in_a_reaction = True
                    sub_sp.sub_species = {}
                    sub_sp.parent_species = sp_name
                    sub_sp_list.append(sub_sp)

            #if sub_sp_name not in SD.Dict.keys():
            for sub_sp in sub_sp_list:
                SD.Dict[sub_sp.name] = sub_sp
                SD.Dict[sub_sp.parent_species].sub_species.update({sub_sp.compartment_name: sub_sp})


        return Counter(compartment_counts)

    # def replace_sub_species_in_reactions(self, SD):
    #     """
    #     New species may be created to live on boundaries
    #     TODO: this may cause issues if new properties are added to SpeciesContainer
    #     """
    #     sp_to_replace = []
    #     for rxn in self.Dict.values():
    #         for sp_name, sp in rxn.involved_species_link.items():
    #             if set(sp.sub_species.keys()).intersection(rxn.involved_compartments):
    #             #if sp.sub_species:
    #                 print(sp.sub_species.items())
    #                 for sub_comp, sub_sp in sp.sub_species.items():
    #                     sub_sp_name = sub_sp.name

    #                     rxn.LHS = [sub_sp_name if x==sp_name else x for x in rxn.LHS]
    #                     rxn.RHS = [sub_sp_name if x==sp_name else x for x in rxn.RHS]
    #                     rxn.eqn_f = rxn.eqn_f.subs({sp_name: sub_sp_name})
    #                     rxn.eqn_r = rxn.eqn_r.subs({sp_name: sub_sp_name})

    #                     sp_to_replace.append((sp_name, sub_sp_name, sub_sp))

    #                     print('Species %s replaced with %s in reaction %s!!!' % (sp_name, sub_sp_name, rxn.name))

    #                 rxn.name = rxn.name + ' [modified]'

    #         for tup in sp_to_replace:
    #             sp_name, sub_sp_name, sub_sp = tup
    #             rxn.involved_species.remove(sp_name)
    #             rxn.involved_species.add(sub_sp_name)
    #             rxn.involved_species_link.pop(sp_name, None)
    #             rxn.involved_species_link.update({sub_sp_name: sub_sp})



    def reaction_to_fluxes(self):
        self.doToAll('reaction_to_fluxes')
        fluxList = []
        for rxn in self.Dict.values():
            for f in rxn.fluxList:
                fluxList.append(f)
        self.fluxList = fluxList
    def get_flux_container(self):
        return FluxContainer(Dict=odict([(f.flux_name, f) for f in self.fluxList]))


class Reaction(_ObjectInstance):
    def __init__(self, name, Dict=None, eqn_f_str=None, eqn_r_str=None, explicit_restriction_to_domain=False):
        if eqn_f_str:
            print("Reaction %s: using the specified equation for the forward flux: %s" % (name, eqn_f_str))
            self.eqn_f = parse_expr(eqn_f_str)
        if eqn_r_str:
            print("Reaction %s: using the specified equation for the reverse flux: %s" % (name, eqn_r_str))
            self.eqn_r = parse_expr(eqn_r_str)
        self.explicit_restriction_to_domain = explicit_restriction_to_domain
        super().__init__(name, Dict)

    def initialize_flux_equations_for_known_reactions(self, reaction_database={}):
        """
        Generates unsigned forward/reverse flux equations for common/known reactions
        """
        if self.reaction_type == 'mass_action':
            rxnSymStr = self.paramDict['on']
            for sp_name in self.LHS:
                rxnSymStr += '*' + sp_name
            self.eqn_f = parse_expr(rxnSymStr)

            rxnSymStr = self.paramDict['off']
            for sp_name in self.RHS:
                rxnSymStr += '*' + sp_name
            self.eqn_r = parse_expr(rxnSymStr)

        elif self.reaction_type == 'mass_action_forward':
            rxnSymStr = self.paramDict['on']
            for sp_name in self.LHS:
                rxnSymStr += '*' + sp_name
            self.eqn_f = parse_expr(rxnSymStr)

        elif self.reaction_type in reaction_database.keys():
            self.custom_reaction(reaction_database[self.reaction_type])

        else:
            raise Exception("Reaction %s does not seem to have an associated equation" % self.name)


    def custom_reaction(self, symStr):
        rxnExpr = parse_expr(symStr)
        rxnExpr = rxnExpr.subs(self.paramDict)
        rxnExpr = rxnExpr.subs(self.speciesDict)
        self.eqn_f = rxnExpr

    def get_involved_species_and_compartments(self, SD=None, CD=None):
        # used to get number of active species in each compartment
        self.involved_species = set(self.LHS + self.RHS)
        for eqn in ['eqn_r', 'eqn_f']:
            if hasattr(self, eqn):
                varSet = {str(x) for x in self.eqn_f.free_symbols}
                spSet = varSet.intersection(SD.Dict.keys())
                self.involved_species = self.involved_species.union(spSet)

        self.involved_compartments = dict(set([(SD.Dict[sp_name].compartment_name, SD.Dict[sp_name].compartment) for sp_name in self.involved_species]))
        if self.explicit_restriction_to_domain:
            self.involved_compartments.update({self.explicit_restriction_to_domain: CD.Dict[self.explicit_restriction_to_domain]})

        if len(self.involved_compartments) not in (1,2):
            raise Exception("Number of compartments involved in a flux must be either one or two!")

    def reaction_to_fluxes(self):
        self.fluxList = []
        all_species = self.LHS + self.RHS
        unique_species = set(all_species)
        for species_name in unique_species:
            stoich = all_species.count(species_name)

            if hasattr(self, 'eqn_f'):
                flux_name = self.name + ' (f) [' + species_name + ']'
                sign = -1 if species_name in self.LHS else 1
                signed_stoich = sign*stoich
                self.fluxList.append(Flux(flux_name, species_name, self.eqn_f, signed_stoich, self.involved_species_link,
                                          self.paramDictValues, self.group, self.explicit_restriction_to_domain))
            if hasattr(self, 'eqn_r'):
                flux_name = self.name + ' (r) [' + species_name + ']'
                sign = 1 if species_name in self.LHS else -1
                signed_stoich = sign*stoich
                self.fluxList.append(Flux(flux_name, species_name, self.eqn_r, signed_stoich, self.involved_species_link,
                                          self.paramDictValues, self.group, self.explicit_restriction_to_domain))





class FluxContainer(_ObjectContainer):
    def __init__(self, df=None, Dict=None):
        super().__init__(Flux, df, Dict)
        # self.propertyList = ['species_name', 'symEqn', 'sign', 'involved_species',
        #                      'involved_parameters', 'source_compartment', 
        #                      'destination_compartment', 'ukeys', 'group']

        self.propertyList = ['species_name', 'symEqn', 'signed_stoich', 'ukeys']#'source_compartment', 'destination_compartment', 'ukeys']
    def check_and_replace_sub_species(self, SD, CD, config):
        fluxes_to_remove = []
        for flux_name, f in self.Dict.items():
            tagged_for_removal = False
            for sp_name, sp in f.spDict.items():
                if sp.sub_species and (f.destination_compartment in sp.sub_species.keys()
                                     or f.source_compartment in sp.sub_species.keys()):
                    tagged_for_removal = True
                    print("flux %s tagged for removal" % flux_name)
                    #for sub_sp_name in sp.sub_species.keys():
                    for sub_sp in sp.sub_species.values():
                        if sub_sp.compartment_name in f.involved_compartments:
                            f.symEqn = f.symEqn.subs({sp_name: sub_sp.name})
                            print("subbed %s for %s" % (sp_name, sub_sp.name))

            if tagged_for_removal:
                fluxes_to_remove.append(f)
                tagged_for_removal = False

        new_flux_list = []
        for f in fluxes_to_remove:
            #if SD.Dict[f.species_name].compartment_name == f.source_compartment:
            new_flux_name = f.flux_name + ' [sub**]'
            involved_species = [str(x) for x in f.symEqn.free_symbols if str(x) in SD.Dict.keys()]
            if not SD.Dict[f.species_name].sub_species:
                new_species_name = f.species_name
            else:
                new_species_name = SD.Dict[f.species_name].sub_species[f.source_compartment].name

            involved_species += [new_species_name] # add the flux species
            species_w_parent = [SD.Dict[x] for x in involved_species if SD.Dict[x].parent_species]
        #if f.species_name not in parent_species:

            print("symEqn")
            print(f.symEqn)
            print("free symbols = ")
            print([str(x) for x in f.symEqn.free_symbols])
            print("involved species = ")
            print(involved_species)
            spDict = {}
            for sp_name in involved_species:
                spDict.update({sp_name: SD.Dict[sp_name]})

            new_flux = Flux(new_flux_name, new_species_name, f.symEqn, f.signed_stoich, spDict, f.paramDict, f.group, f.explicit_restriction_to_domain)
            new_flux.get_additional_flux_properties(CD, config)

            # get length scale factor
            comp1 = SD.Dict[species_w_parent[0].parent_species].compartment
            comp2 = species_w_parent[0].compartment_name
            print(comp1.name)
            #print(comp2)
            length_scale_factor = comp1.scale_to[comp2]
            print("computed length_scale_factor")
            setattr(new_flux, 'length_scale_factor', length_scale_factor)
        
            new_flux_list.append((new_flux_name, new_flux))
            #else:
            #    new_species_name = 
            #    print("species name, source compartment: %s, %s" % (f.species_name, f.source_compartment))

        for flux_rm in fluxes_to_remove:
            Print('removing flux %s' %  flux_rm.flux_name)
            self.Dict.pop(flux_rm.flux_name)

        for (new_flux_name, new_flux) in new_flux_list:
            Print('adding flux %s' % new_flux_name)
            self.Dict.update({new_flux_name: new_flux})

class Flux(_ObjectInstance):
    def __init__(self, flux_name, species_name, symEqn, signed_stoich, spDict, paramDict, group, explicit_restriction_to_domain=None):
        super().__init__(flux_name)

        self.flux_name = flux_name
        self.species_name = species_name
        self.symEqn = symEqn
        self.signed_stoich = signed_stoich
        self.spDict = spDict
        self.paramDict = paramDict
        self.group = group
        self.explicit_restriction_to_domain = explicit_restriction_to_domain

        self.symList = [str(x) for x in symEqn.free_symbols]
        self.lambdaEqn = sympy.lambdify(self.symList, self.symEqn, modules=['sympy'])
        self.involved_species = list(spDict.keys())
        self.involved_parameters = list(paramDict.keys())


    def get_additional_flux_properties(self, CD, config):
        # get additional properties of the flux
        self.get_involved_species_parameters_compartment(CD)
        self.get_flux_dimensionality()
        self.get_boundary_marker()
        self.get_flux_units()
        self.get_is_linear()
        self.get_is_linear_comp()
        self.get_ukeys(config)
        self.get_integration_measure(CD, config)

    def get_involved_species_parameters_compartment(self, CD):
        symStrList = {str(x) for x in self.symList}
        self.involved_species = symStrList.intersection(self.spDict.keys())
        self.involved_species.add(self.species_name)
        self.involved_parameters = symStrList.intersection(self.paramDict.keys())

        # truncate spDict and paramDict so they only contain the species and parameters we need
        self.spDict = dict((k, self.spDict[k]) for k in self.involved_species if k in self.spDict)
        self.paramDict = dict((k, self.paramDict[k]) for k in self.involved_parameters if k in self.paramDict)

        #self.involved_compartments = set([sp.compartment for sp in self.spDict.values()])
        self.involved_compartments = dict([(sp.compartment.name, sp.compartment) for sp in self.spDict.values()])

        if self.explicit_restriction_to_domain:
            self.involved_compartments.update({self.explicit_restriction_to_domain: CD.Dict[self.explicit_restriction_to_domain]})
        if len(self.involved_compartments) not in (1,2):
            raise Exception("Number of compartments involved in a flux must be either one or two!")
    #def flux_to_dolfin(self):

    def get_flux_dimensionality(self):
        destination_compartment = self.spDict[self.species_name].compartment
        destination_dim = destination_compartment.dimensionality
        comp_names = set(self.involved_compartments.keys())
        comp_dims = set([comp.dimensionality for comp in self.involved_compartments.values()])
        comp_names.remove(destination_compartment.name)
        comp_dims.remove(destination_dim)

        if len(comp_names) == 0:
            self.flux_dimensionality = [destination_dim]*2
            self.source_compartment = destination_compartment.name
        else:
            source_dim = comp_dims.pop()
            self.flux_dimensionality = [source_dim, destination_dim]
            self.source_compartment = comp_names.pop()

        self.destination_compartment = destination_compartment.name

    def get_boundary_marker(self):
        dim = self.flux_dimensionality
        if dim[1] <= dim[0]:
            self.boundary_marker = None
        elif dim[1] > dim[0]: # boundary flux
            self.boundary_marker = self.involved_compartments[self.source_compartment].cell_marker

    def get_flux_units(self):
        sp = self.spDict[self.species_name]
        compartment_units = sp.compartment.compartment_units
        # a boundary flux
        if (self.boundary_marker and self.flux_dimensionality[1]>self.flux_dimensionality[0]) or sp.parent_species:
            self.flux_units = sp.concentration_units / compartment_units * sp.D_units
        else:
            self.flux_units = sp.concentration_units / ureg.s

    def get_is_linear(self):
        """
        For a given flux we want to know which terms are linear
        """
        is_linear_wrt = {}
        for symVar in self.symList:
            varName = str(symVar)
            if varName in self.involved_species:
                if sympy.diff(self.symEqn, varName , 2).is_zero:
                    is_linear_wrt[varName] = True
                else:
                    is_linear_wrt[varName] = False

        self.is_linear_wrt = is_linear_wrt

    def get_is_linear_comp(self):
        """
        Is the flux linear in terms of a compartment vector (e.g. dj/du['pm'])
        """
        is_linear_wrt_comp = {}
        umap = {}

        for varName in self.symList:
            if varName in self.involved_species:
                compName = self.spDict[varName].compartment_name
                umap.update({varName: 'u'+compName})

        newEqn = self.symEqn.subs(umap)

        for compName in self.involved_compartments:
            if sympy.diff(newEqn, 'u'+compName, 2).is_zero:
                is_linear_wrt_comp[compName] = True
            else:
                is_linear_wrt_comp[compName] = False

        self.is_linear_wrt_comp = is_linear_wrt_comp

    def get_integration_measure(self, CD, config):
        sp = self.spDict[self.species_name]
        flux_dim = self.flux_dimensionality
        min_dim = min(CD.get_property('dimensionality').values())
        max_dim = max(CD.get_property('dimensionality').values())

        # boundary flux
        if flux_dim[0] < flux_dim[1]:
            self.int_measure = sp.compartment.ds(self.boundary_marker)
        # volumetric flux (max dimension)
        elif flux_dim[0] == flux_dim[1] == max_dim:
            self.int_measure = sp.compartment.dx
        # volumetric flux (min dimension)
        elif flux_dim[1] == min_dim < max_dim:
            if config.settings['ignore_surface_diffusion']:
                self.int_measure = sp.compartment.dP
            else:
                self.int_measure = sp.compartment.dx
        else:
            raise Exception("I'm not sure what integration measure to use on a flux with this dimensionality")

    def get_ukeys(self, config):
        """
        Given the dimensionality of a flux (e.g. 2d surface to 3d vol) and the dimensionality
        of a species, determine which term of u should be used
        """
        self.ukeys = {}
        flux_vars = [str(x) for x in self.symList if str(x) in self.involved_species]
        for var_name in flux_vars:
            self.ukeys[var_name] = self.get_ukey(var_name, config)

    def get_ukey(self, var_name, config):
        sp = self.spDict[self.species_name]
        var = self.spDict[var_name]

        # boundary fluxes (surface -> volume)
        #if var.dimensionality < sp.dimensionality: 
        if var.dimensionality < sp.compartment.dimensionality: 
            return 'u' # always true if operator splitting to decouple compartments

        if sp.name == var.parent_species:
            return 'u'

        if config.solver['nonlinear'] == 'picard':# or 'IMEX':
            # volume -> surface
            if var.dimensionality > sp.dimensionality and config.settings['add_boundary_species']:
                if self.is_linear_wrt_comp[var.compartment_name]:
                    return 'bt'
                else:
                    return 'bk'

            elif var.dimensionality > sp.dimensionality:
                return 'b'+sp.compartment_name

            # volumetric fluxes
            elif var.compartment_name == self.destination_compartment:
                if self.is_linear_wrt_comp[var.compartment_name]:
                    return 't'
                #dynamic LHS
                elif var.name == sp.name and self.is_linear_wrt[sp.name]:
                    return 't'
                else:
                    return 'k'

        elif config.solver['nonlinear'] == 'newton':
            return 'u'

        elif config.solver['nonlinear'] == 'IMEX':
            ## same compartment
            # dynamic LHS
            # if var.name == sp.name:
            #     if self.is_linear_wrt[sp.name]:
            #         return 't'
            #     else:
            #         return 'n'
            # static LHS
            if var.compartment_name == sp.compartment_name:
                if self.is_linear_wrt_comp[sp.compartment_name]:
                    return 't'
                else:
                    return 'n'
            ## different compartments
            # volume -> surface
            if var.dimensionality > sp.dimensionality:
                return 'b'+sp.compartment_name
            # surface -> volume is covered by first if statement in get_ukey()




            # if sp.dimensionality == 3: #TODO fix this
            #     if var.compartment_name == sp.compartment_name and self.is_linear_wrt_comp[var.compartment_name]:
            #         return 't'
            #     else:
            #         if var.name == sp.name and self.is_linear_wrt[sp.name]:
            #             return 't'
            #         else:
            #             return 'k'
            # # volume -> surface
            # elif var.dimensionality > sp.dimensionality:
            #     return 'b'+sp.compartment_name
            # else:
            #     if self.is_linear_wrt_comp[var.compartment_name]:
            #         return 't'
            #     else:
            #         return 'k'

        # elif config.solver['nonlinear'] == 'IMEX':
        #     if 
        #     return 'n'

        raise Exception("If you made it to this far in get_ukey() I missed some logic...") 


    # def flux_to_dolfin(self):
    #     value_dict = {}
    #     unit_dict = {}

    #     for var_name in [str(x) for x in self.symList]:
    #         if var_name in self.paramDict.keys():
    #             var = self.paramDict[var_name]
    #             if var.is_time_dependent:
    #                 value_dict[var_name] = var.dolfinConstant.get()
    #             else:
    #                 value_dict[var_name] = var.value_unit.magnitude
    #             unit_dict[var_name] = var.value_unit.units * 1 # turns unit into "Quantity" class
    #         elif var_name in self.spDict.keys():
    #             var = self.spDict[var_name]
    #             ukey = self.ukeys[var_name]
    #             if ukey[0] == 'b':
    #                 if not var.parent_species:
    #                     sub_species = var.sub_species[self.destination_compartment]
    #                     value_dict[var_name] = sub_species.u[ukey[1]]
    #                     print("Species %s substituted for %s in flux %s" % (var_name, sub_species.name, self.name))
    #                 else:
    #                     value_dict[var_name] = var.u[ukey[1]]
    #             else:
    #                 value_dict[var_name] = var.u[ukey]

    #             unit_dict[var_name] = var.concentration_units * 1

    #     prod = self.lambdaEqn(**value_dict)
    #     unit_prod = self.lambdaEqn(**unit_dict)
    #     unit_prod = 1 * (1*unit_prod).units # trick to make object a "Quantity" class

    #     self.prod = prod
    #     self.unit_prod = unit_prod


    def flux_to_dolfin(self, config):
        value_dict = {}

        for var_name in [str(x) for x in self.symList]:
            if var_name in self.paramDict.keys():
                var = self.paramDict[var_name]
                if var.is_time_dependent:
                    value_dict[var_name] = var.dolfinConstant * var.unit
                else:
                    value_dict[var_name] = var.value_unit
            elif var_name in self.spDict.keys():
                var = self.spDict[var_name]
                ukey = self.ukeys[var_name]
                if ukey[0] == 'b' and config.settings['add_boundary_species']:
                    if not var.parent_species and config.settings['add_boundary_species']:
                        sub_species = var.sub_species[self.destination_compartment]
                        value_dict[var_name] = sub_species.u[ukey[1]]
                        Print("Species %s substituted for %s in flux %s" % (var_name, sub_species.name, self.name))
                    else:
                        value_dict[var_name] = var.u[ukey[1]]
                else:
                    value_dict[var_name] = var.u[ukey]

                value_dict[var_name] *= var.concentration_units * 1

        eqn_eval = self.lambdaEqn(**value_dict)
        prod = eqn_eval.magnitude
        unit_prod = 1 * (1*eqn_eval.units).units
        #unit_prod = self.lambdaEqn(**unit_dict)
        #unit_prod = 1 * (1*unit_prod).units # trick to make object a "Quantity" class

        self.prod = prod
        self.unit_prod = unit_prod




# ==============================================================================
# ==============================================================================
# Model class consists of parameters, species, etc. and is used for simulation
# ==============================================================================
# ==============================================================================

class Model(object):
    def __init__(self, PD, SD, CD, RD, FD, config):
        self.PD = PD
        self.SD = SD
        self.CD = CD
        self.RD = RD
        self.FD = FD
        self.config = config

        self.u = SD.u
        self.v = SD.v
        self.V = SD.V

        self.params = ddict(list)

        self.idx = 0
        self.t = 0.0
        self.dt = config.solver['initial_dt']
        self.T = d.Constant(self.t)
        self.dT = d.Constant(self.dt)
        self.t_final = config.solver['T']
        self.linear_iterations = None

        self.timers = {}
        self.timings = ddict(list)

        self.Forms = FormContainer()
        self.a = {}
        self.L = {}
        self.F = {}
        self.nonlinear_solver = {}
        self.scipy_odes = {}

        self.data = stubs.data_manipulation.Data(config)


    def assemble_reactive_fluxes(self):
        """
        Creates the actual dolfin objects for each flux. Checks units for consistency
        """
        for j in self.FD.Dict.values():
            total_scaling = 1.0 # all adjustments needed to get congruent units
            sp = j.spDict[j.species_name]
            prod = j.prod
            unit_prod = j.unit_prod
            # first, check unit consistency
            if (unit_prod/j.flux_units).dimensionless:
                setattr(j, 'scale_factor', 1*ureg.dimensionless)
                pass
            else:
                if hasattr(j, 'length_scale_factor'):
                    Print("Adjusting flux for %s by the provided length scale factor." % (j.name, j.length_scale_factor))
                    length_scale_factor = getattr(j, 'length_scale_factor')
                else:
                    if len(j.involved_compartments.keys()) < 2:
                        Print("Units of flux: %s" % unit_prod)
                        Print("Desired units: %s" % j.flux_units)
                        raise Exception("Flux %s seems to be a boundary flux (or has inconsistent units) but only has one compartment, %s." 
                            % (j.name, j.destination_compartment))
                    length_scale_factor = j.involved_compartments[j.source_compartment].scale_to[j.destination_compartment]

                Print(('\nThe flux, %s, from compartment %s to %s, has units ' %
                       (j.flux_name, j.source_compartment, j.destination_compartment) + colored(unit_prod, "red") +
                       "...the desired units for this flux are " + colored(j.flux_units, "cyan")))
                Print('Adjusted flux with the length scale factor ' + 
                      colored("%f [%s]"%(length_scale_factor.magnitude,str(length_scale_factor.units)), "cyan") + ' to match units.\n') 

                if (length_scale_factor*unit_prod/j.flux_units).dimensionless:
                    prod *= length_scale_factor.magnitude
                    total_scaling *= length_scale_factor.magnitude
                    unit_prod *= length_scale_factor.units*1
                    setattr(j, 'length_scale_factor', length_scale_factor)
                elif (1/length_scale_factor*unit_prod/j.flux_units).dimensionless:
                    prod /= length_scale_factor.magnitude
                    total_scaling /= length_scale_factor.magnitude
                    unit_prod /= length_scale_factor.units*1
                    setattr(j, 'length_scale_factor', 1/length_scale_factor)
                else:
                    raise Exception("Inconsitent units!")

                                

            # if units are consistent in dimensionality but not magnitude, adjust values
            if j.flux_units != unit_prod:
                unit_scaling = unit_prod.to(j.flux_units).magnitude
                total_scaling *= unit_scaling
                prod *= unit_scaling
                Print(('\nThe flux, %s, has units '%j.flux_name + colored(unit_prod, "red") +
                    "...the desired units for this flux are " + colored(j.flux_units, "cyan")))
                Print('Adjusted value of flux by ' + colored("%f"%unit_scaling, "cyan") + ' to match units.\n')
                setattr(j, 'unit_scaling', unit_scaling)
            else:
                setattr(j, 'unit_scaling', 1)

            setattr(j, 'total_scaling', total_scaling)

            # adjust sign+stoich if necessary
            prod *= j.signed_stoich

            # multiply by appropriate integration measure and test function
            if j.flux_dimensionality[0] < j.flux_dimensionality[1]:
                form_key = 'B'
            else:
                form_key = 'R'
            prod = prod*sp.v*j.int_measure

            setattr(j, 'dolfin_flux', prod)

            BRform = -prod # by convention, terms are all defined as if they were on the LHS of the equation e.g. F(u;v)=0
            self.Forms.add(Form(BRform, sp, form_key, flux_name=j.name))


    def assemble_diffusive_fluxes(self):
        min_dim = min(self.CD.get_property('dimensionality').values())
        max_dim = max(self.CD.get_property('dimensionality').values())
        dT = self.dT

        for sp_name, sp in self.SD.Dict.items():
            if sp.is_in_a_reaction:
                if self.config.solver['nonlinear'] == 'picard' or 'IMEX':
                    u = sp.u['t']
                elif self.config.solver['nonlinear'] == 'newton':
                    u = sp.u['u']
                un = sp.u['n']
                v = sp.v
                D = sp.D

                if sp.dimensionality == max_dim and not sp.parent_species:
                    #or not self.config.settings['ignore_surface_diffusion']:
                    dx = sp.compartment.dx
                    Dform = D*d.inner(d.grad(u), d.grad(v)) * dx
                    self.Forms.add(Form(Dform, sp, 'D'))
                elif sp.dimensionality < max_dim or sp.parent_species:
                    if self.config.settings['ignore_surface_diffusion']:
                        dx=sp.compartment.dP
                    else:
                        dx = sp.compartment.dx
                        Dform = D*d.inner(d.grad(u), d.grad(v)) * dx
                        self.Forms.add(Form(Dform, sp, 'D'))

                #if sp.dimensionality == max_dim or not self.config.settings['ignore_surface_diffusion']:
                #    dx = sp.compartment.dx
                #    Dform = D*d.inner(d.grad(u), d.grad(v)) * dx
                #    self.Forms.add(Form(Dform, sp, 'D'))
                #elif sp.dimensionality < max_dim and self.config.settings['ignore_surface_diffusion']:
                #    dx = sp.compartment.dP

                # time derivative
                #Mform = (u-un)/dT * v * dx
                #self.Forms.add(Form(Mform, sp, 'M'))
                Mform_u = u/dT * v * dx
                Mform_un = -un/dT * v * dx
                self.Forms.add(Form(Mform_u, sp, "Mu"))
                self.Forms.add(Form(Mform_un, sp, "Mun"))

            else:
                Print("Species %s is not in a reaction?" %  sp_name)

    def set_allow_extrapolation(self):
        for comp_name in self.u.keys():
            ucomp = self.u[comp_name] 
            for func_key in ucomp.keys():
                if func_key != 't': # trial function by convention
                    self.u[comp_name][func_key].set_allow_extrapolation(True)

#===============================================================================
#===============================================================================
# SOLVING
#===============================================================================
#===============================================================================
    def set_time(self, t, dt=None):
        if not dt:
            dt = self.dt
        else:
            Print("dt changed from %f to %f" % (self.dt, dt))
        self.t = t
        self.T.assign(t)
        self.dt = dt
        self.dT.assign(dt) 

        Print("New time: %f" % self.t)

    def forward_time_step(self, factor=1):
        self.dT.assign(float(self.dt*factor))
        self.t = float(self.t+self.dt*factor)
        self.T.assign(self.t)

        #print("t: %f , dt: %f" % (self.t, self.dt*factor))

    def stopwatch(self, key, stop=False):
        if key not in self.timers.keys():
            self.timers[key] = d.Timer()
        if not stop:
            self.timers[key].start()
        else:
            elapsed_time = self.timers[key].elapsed()[0]
            Print("%s finished in %f seconds" % (key,elapsed_time))
            self.timers[key].stop()
            self.timings[key].append(elapsed_time)
            return elapsed_time

#    def solver_step_forward(self):
#
#        self.update_time()


    def updateTimeDependentParameters(self, t=None): 
        if not t:
            # custom time
            t = self.t
        for param_name, param in self.PD.Dict.items():
            if param.is_time_dependent:
                newValue = param.symExpr.subs({'t': t}).evalf()
                param.dolfinConstant.assign(newValue)
                Print('%f assigned to time-dependent parameter %s' % (newValue, param.name))
                self.params[param_name].append((t,newValue))

    def strang_RDR_step_forward(self):
        self.idx += 1
        Print('\n\n ***Beginning time-step %d: time=%f, dt=%f\n\n' % (self.idx, self.t, self.dt))

        # first reaction step (half time step) t=[t,t+dt/2]
        self.boundary_reactions_forward_scipy('pm', factor=0.5, method='BDF', rtol=1e-5, atol=1e-8)
        self.set_time(self.t-self.dt/2) # reset time back to t
        self.boundary_reactions_forward_scipy('er', factor=0.5, all_dofs=True, method='RK45', rtol=1e-5, atol=1e-8)
        self.update_solution_boundary_to_volume()

        # diffusion step (full time step) t=[t,t+dt]

        self.set_time(self.t-self.dt/2) # reset time back to t
        self.diffusion_forward('cyto', factor=1) 
        self.update_solution_volume_to_boundary()
        #self.SD.Dict['A_sub_pm'].u['u'].interpolate(self.u['cyto']['u'])

        # second reaction step (half time step) t=[t+dt/2,t+dt]
        self.set_time(self.t-self.dt/2) # reset time back to t+dt/2
        self.boundary_reactions_forward_scipy('pm', factor=0.5, method='BDF', rtol=1e-5, atol=1e-8)
        self.set_time(self.t-self.dt/2) # reset time back to t
        self.boundary_reactions_forward_scipy('er', factor=0.5, all_dofs=True, method='RK45', rtol=1e-5, atol=1e-8)
        self.update_solution_boundary_to_volume()

        #print("finished second reaction step: t = %f, dt = %f (%d picard iterations)" % (self.t, self.dt, self.pidx))

        #if self.pidx >= self.config.solver['max_picard']:
        #    self.set_time(self.t, dt=self.dt*self.config.solver['dt_decrease_factor'])
        #    print("Decreasing step size")
        #if self.pidx < self.config.solver['min_picard']:
        #    self.set_time(self.t, dt=self.dt*self.config.solver['dt_increase_factor'])
        #    print("Increasing step size")

        self.update_solution()
        Print("\n Finished step %d of RDR with final time: %f" % (self.idx, self.t))



    def strang_RD_step_forward(self):
        self.idx += 1
        Print('\n\n ***Beginning time-step %d: time=%f, dt=%f\n\n' % (self.idx, self.t, self.dt))

        # first reaction step (half time step) t=[t,t+dt/2]
        self.boundary_reactions_forward(factor=0.5)
        Print("finished reaction step: t = %f, dt = %f (%d picard iterations)" % (self.t, self.dt, self.pidx))
        # transfer values of solution onto volumetric field
        self.update_solution_boundary_to_volume()

        self.diffusion_forward('cyto', factor=0.5) 
        Print("finished diffusion step: t = %f, dt = %f (%d picard iterations)" % (self.t, self.dt, self.pidx))
        self.update_solution_volume_to_boundary()

        if self.pidx >= self.config.solver['max_picard']:
            self.set_time(self.t, dt=self.dt*self.config.solver['dt_decrease_factor'])
            Print("Decrease step size")
        if self.pidx < self.config.solver['min_picard']:
            self.set_time(self.t, dt=self.dt*self.config.solver['dt_increase_factor'])
            Print("Increasing step size")

        Print("\n Finished step %d of RD with final time: %f" % (self.idx, self.t))

    def IMEX_2SBDF(self, method='RK45'):
        self.idx += 1
        Print('\n\n ***Beginning time-step %d: time=%f, dt=%f\n\n' % (self.idx, self.t, self.dt))

        self.boundary_reactions_forward_scipy('pm', factor=0.5, method=method)
        self.set_time(self.t-self.dt/2) # reset time back to t
        self.boundary_reactions_forward_scipy('er', factor=0.5, all_dofs=True, method='RK45', rtol=1e-5, atol=1e-8)
        self.update_solution_boundary_to_volume()
   
        self.set_time(self.t-self.dt/2) # reset time back to t
        self.IMEX_order2_diffusion_forward('cyto', factor=1)
        self.update_solution_volume_to_boundary()

        self.set_time(self.t-self.dt/2) # reset time back to t+dt/2
        self.boundary_reactions_forward_scipy('pm', factor=0.5, method=method, rtol=1e-5, atol=1e-8)
        self.set_time(self.t-self.dt/2) # reset time back to t+dt/2
        self.boundary_reactions_forward_scipy('er', factor=0.5, all_dofs=True, method='RK45')

        self.update_solution_boundary_to_volume()



    def IMEX_1BDF(self, method='RK45'):
        self.stopwatch("Total time step")
        self.idx += 1
        Print('\n\n ***Beginning time-step %d: time=%f, dt=%f\n\n' % (self.idx, self.t, self.dt))

        self.boundary_reactions_forward_scipy('pm', factor=0.5, method=method, rtol=1e-5, atol=1e-8)
        self.set_time(self.t-self.dt/2) # reset time back to t
        self.boundary_reactions_forward_scipy('er', factor=0.5, all_dofs=True, method='RK45')
        self.update_solution_boundary_to_volume()
       

        self.set_time(self.t-self.dt/2) # reset time back to t
        self.IMEX_order1_diffusion_forward('cyto', factor=1)
        self.update_solution_volume_to_boundary()

        self.set_time(self.t-self.dt/2) # reset time back to t+dt/2
        self.boundary_reactions_forward_scipy('pm', factor=0.5, method=method, rtol=1e-5, atol=1e-8)
        self.set_time(self.t-self.dt/2) # reset time back to t+dt/2
        self.boundary_reactions_forward_scipy('er', factor=0.5, all_dofs=True, method='RK45')
        self.update_solution_boundary_to_volume()

        if self.linear_iterations >= self.config.solver['linear_maxiter']:
            self.set_time(self.t, dt=self.dt*self.config.solver['dt_decrease_factor'])
            Print("Decreasing step size")
        if self.linear_iterations < self.config.solver['linear_miniter']:
            self.set_time(self.t, dt=self.dt*self.config.solver['dt_increase_factor'])
            Print("Increasing step size")

        self.stopwatch("Total time step", stop=True)

        #self.u['cyto']['n'].assign(self.u['cyto']['u'])


    def reset_timestep(self, comp_list=[]):
        """
        Resets the time back to what it was before the time-step. Optionally, input a list of compartments
        to have their function values reset (['n'] value will be assigned to ['u'] function).
        """
        self.set_time(self.t - self.dt, self.dt*self.config.solver['dt_decrease_factor'])
        Print("Resetting time-step and decreasing step size")
        for comp_name in comp_list:
            self.u[comp_name]['n'].assign(self.u[comp_name]['u'])
            Print("Assigning old value of u to species in compartment %s" % comp_name)

#    def adaptive_solver(self):
#


    def IMEX_order1_diffusion_forward(self, comp_name, factor=1):
        self.stopwatch("Diffusion step")
        self.forward_time_step(factor=factor)
        self.updateTimeDependentParameters()
        d.parameters['form_compiler']['optimize'] = True
        d.parameters['form_compiler']['cpp_optimize'] = True

        forms = self.split_forms[comp_name]

        self.stopwatch('A assembly')
        if self.idx <= 1:
            # terms which will not change across time-steps
            self.Abase = d.assemble(forms['Mu'] + forms['D'], form_compiler_parameters={'quadrature_degree': 4}) # +d.lhs(forms["R"])
            self.solver = d.KrylovSolver('cg','hypre_amg')
            self.solver.parameters['nonzero_initial_guess'] = True


#        # if the time step size changed we need to reassemble the LHS matrix...
#        if self.idx > 1 and (self.linear_iterations >= self.config.solver['linear_maxiter'] or
#           self.linear_iterations < self.config.solver['linear_miniter']):
#            self.stopwatch('A assembly')
#            self.A = d.assemble(forms['Mu'] + forms['D'] + d.lhs(forms['R'] + d.lhs(forms['B'])), form_compiler_parameters={'quadrature_degree': 4})
#            self.stopwatch('A assembly', stop=True)
#            self.linear_iterations = 0
#            Print("Reassembling A because of change in time-step")
#
#        # sanity check to make sure A is not changing
#        if self.idx == 2:
#            Anew = d.assemble(forms['Mu'] + forms['D'] + d.lhs(forms['R'] + d.lhs(forms['B'])), form_compiler_parameters={'quadrature_degree': 4})
#            Print("Ainit linf norm = %f" % self.A.norm('linf'))
#            Print("Anew linf norm = %f" % Anew.norm('linf'))
#            assert np.abs(self.A.norm('linf') - Anew.norm('linf')) < 1e-10

        # full assembly in 1 step requires using previous time step value of volumetric species for boundary fluxes
        self.A = self.Abase + d.assemble(d.lhs(forms['B'] + forms['R']), form_compiler_parameters={'quadrature_degree': 4})
        self.stopwatch('A assembly', stop=True)

        self.stopwatch('b assembly')
        b = d.assemble(-forms['Mun'] +  d.rhs(forms['B'] + forms['R']), form_compiler_parameters={'quadrature_degree': 4})
        self.stopwatch('b assembly', stop=True)

        U = self.u[comp_name]['u'].vector()
        self.linear_iterations = self.solver.solve(self.A, U, b)

        self.u[comp_name]['n'].assign(self.u[comp_name]['u'])

        self.stopwatch("Diffusion step", stop=True)
        Print("Diffusion step finished in %d iterations" % self.linear_iterations)
        


    def IMEX_order2_diffusion_forward(self, comp_name, factor=1):
        self.stopwatch("Diffusion step")
        self.forward_time_step(factor=factor)
        self.updateTimeDependentParameters()

        forms = self.split_forms[comp_name]

        if self.idx <= 1:
            # F = forms['Mu'] + forms['Mun'] + forms['D'] + forms['R'] + forms['B']
            # self.a[comp_name] = d.lhs(F)
            # self.L[comp_name] = d.rhs(F)

            # terms which will not change across time-steps
            self.stopwatch('A assembly')
            self.A = d.assemble(3/2*forms['Mu'] + forms['D'] + d.lhs(forms['R'] + d.lhs(forms['B'])), form_compiler_parameters={'quadrature_degree': 4})
            self.solver = d.KrylovSolver('cg','hypre_amg')
            self.solver.parameters['nonzero_initial_guess'] = True

            Ainit = d.assemble(forms['Mu'] + forms['D'] + d.lhs(forms['R'] + d.lhs(forms['B'])), form_compiler_parameters={'quadrature_degree': 4})
            self.stopwatch('A assembly', stop=True)
            self.stopwatch('b assembly')
            Mun = d.assemble(-forms['Mun'], form_compiler_parameters={'quadrature_degree': 4})
            BR = d.assemble(d.rhs(forms['R']) + d.rhs(forms['B']), form_compiler_parameters={'quadrature_degree': 4})
            binit = Mun + BR

            self.stopwatch('b assembly', stop=True)
            U = self.u[comp_name]['u'].vector()
            self.solver.solve(Ainit, U, binit)

            self.Mun_old = Mun
            self.BR_old = BR
            return

        # sanity check to make sure A is not changing
        #Anew = d.assemble(forms['Mu'] + forms['D'] + d.lhs(forms['R'] + d.lhs(forms['B'])), form_compiler_parameters={'quadrature_degree': 2})
        #print("A mean: %f" % self.A.array().mean())
        #print("Anew mean: %f" % Anew.array().mean())

        self.stopwatch('b assembly')
        d.parameters['form_compiler']['optimize'] = True
        d.parameters['form_compiler']['cpp_optimize'] = True

        # minus signs here moves terms from LHS (convention) to RHS
        # rhs() implicitly flips sign of term
        Mun = d.assemble(-forms['Mun'], form_compiler_parameters={'quadrature_degree': 3})
        BR = d.assemble(d.rhs(forms['R']) + d.rhs(forms['B']), form_compiler_parameters={'quadrature_degree': 3})

        Mun_rhs = +2*Mun - 1/2 * self.Mun_old
        BR_rhs = 2*BR - self.BR_old

        b = Mun_rhs + BR_rhs

        ##print('Mun max: %f, B max: %f, R max: %f' % (rxn_Mun.max(), rxn_B.max(), rxn_R.max()))
        ##b = rxn_Mun+rxn_B+rxn_R
        self.stopwatch('b assembly', stop=True)
        ##b = d.assemble(rxn, form_compiler_parameters={'quadrature_degree': 2})
        U = self.u[comp_name]['u'].vector()
        #d.solve(self.A, U, b, 'cg', 'hypre_amg')
        self.solver.solve(self.A, U, b)
        #d.parameters["form_compiler"]["quadrature_degree"] = 3
        #d.solve(self.a[comp_name]==self.L[comp_name], self.u[comp_name]['u'], solver_parameters=self.config.dolfin_linear_coarse)

        #self.solver.solve(self.a==self.L, self.u['cyto']['u'])
#            self.F[comp_name] = total_eqn
#            J = d.derivative(self.F[comp_name], self.u[comp_name]['u'])
#            problem = d.NonlinearVariationalProblem(self.F[comp_name], self.u[comp_name]['u'], [], J)
#            self.nonlinear_solver[comp_name] = d.NonlinearVariationalSolver(problem)
#            p = self.nonlinear_solver[comp_name].parameters
#            p['newton_solver'].update(self.config.dolfin_linear_coarse)

#            self.a[comp_name] = d.lhs(total_eqn)
#            self.L[comp_name] = d.rhs(total_eqn)

        #d.solve(self.a[comp_name] == self.L[comp_name], self.u[comp_name]['u'])

        #self.nonlinear_solver[comp_name].solve()

        #self.u[comp_name]['k'].assign(self.u[comp_name]['u'])
        self.Mun_old = Mun
        self.BR_old = BR

        self.u[comp_name]['n'].assign(self.u[comp_name]['u'])

        self.stopwatch("Diffusion step", stop=True)




#    def strang_DR_step_forward(self):
#        self.idx += 1
#        print('\n\n ***Beginning time-step %d: time=%f, dt=%f\n\n' % (self.idx, self.t, self.dt))
#        # diffusion step (full time step) t=[t,t+dt/2]
#        self.diffusion_forward(factor=0.5) 
#        print("finished diffusion step: t = %f, dt = %f (%d picard iterations)" % (self.t, self.dt, self.pidx))
#        self.update_solution_volume_to_boundary()
#
#        # reaction step (half time step) t=[t+dt/2,t+dt]
#        self.boundary_reactions_forward(factor=0.5)
#        print("finished reaction step: t = %f, dt = %f (%d picard iterations)" % (self.t, self.dt, self.pidx))
#        self.update_solution_boundary_to_volume()
#
#
#        if self.pidx >= self.config.solver['max_picard']:
#            self.set_time(self.t, self.dt*self.config.solver['dt_decrease_factor'])
#            print("Decrease step size")
#        if self.pidx < self.config.solver['min_picard']:
#            self.set_time(self.t, self.dt*self.config.solver['dt_increase_factor'])
#            print("Increasing step size")
#
#        print("\n Finished step %d of DR with final time: %f" % (self.idx, self.t))


    def establish_mappings(self):
        for sp_name, sp in self.SD.Dict.items():
            if sp.parent_species:
                sp_parent = self.SD.Dict[sp.parent_species]
                Vsub = self.V[sp.compartment_name]
                submesh = self.CD.meshes[sp.compartment_name]
                V = self.V[sp_parent.compartment_name]
                submesh_species_index = sp.compartment_index
                mesh_species_index = sp_parent.compartment_index

                idx = common.submesh_dof_to_mesh_dof(Vsub, submesh, self.CD.bmesh_emap_0, V,
                                                     submesh_species_index=submesh_species_index,
                                                     mesh_species_index=mesh_species_index)
                sp_parent.dof_map.update({sp_name: idx})

    def update_solution_boundary_to_volume(self):
        for sp_name, sp in self.SD.Dict.items():
            if sp.parent_species:
                sp_parent = self.SD.Dict[sp.parent_species]
                submesh_species_index = sp.compartment_index
                idx = sp_parent.dof_map[sp_name]

                pcomp_name = sp_parent.compartment_name
                comp_name = sp.compartment_name

                self.u[pcomp_name]['n'].vector()[idx] = \
                    stubs.data_manipulation.dolfinGetFunctionValues(self.u[comp_name]['u'], self.V[comp_name], submesh_species_index)

                self.u[pcomp_name]['u'].vector()[idx] = \
                    stubs.data_manipulation.dolfinGetFunctionValues(self.u[comp_name]['u'], self.V[comp_name], submesh_species_index)

                Print("Assigned values from %s (%s) to %s (%s)" % (sp_name, comp_name, sp_parent.name, pcomp_name))

    def update_solution_volume_to_boundary(self):
        for comp_name in self.CD.Dict.keys():
            for key in self.u[comp_name].keys():
                if key[0] == 'b':
                    self.u[comp_name][key].interpolate(self.u[comp_name]['u'])
                    sub_comp_name = key[1:]
                    Print("Interpolated values from compartment %s to %s" % (comp_name, sub_comp_name))

    def update_solution_volume_to_boundary_subspecies(self):
        for sp_name, sp in self.SD.Dict.items():
            if sp.sub_species:
                for comp_name, sp_sub in sp.sub_species.items():
                    sub_name = sp_sub.name
                    submesh_species_index = sp_sub.compartment_index
                    idx = sp.dof_map[sub_name]

                    pcomp_name = sp.compartment_name

                    unew = self.u[pcomp_name]['u'].vector()[idx]

                    stubs.data_manipulation.dolfinSetFunctionValues(self.u[comp_name]['u'], unew, self.V[comp_name], submesh_species_index)
                    stubs.data_manipulation.dolfinSetFunctionValues(self.u[comp_name]['n'], unew, self.V[comp_name], submesh_species_index)
                    Print("Assigned values from %s (%s) to %s (%s)" % (sp_name, pcomp_name, sub_name, comp_name))

    def update_solution_boundary_to_volume_dirichlet(self):
        bcs = []
        for sp_name, sp in self.SD.Dict.items():
            if sp.parent_species:
                sp_parent = self.SD.Dict[sp.parent_species]
                parent_species_index = sp_parent.compartment_index
                submesh_species_index = sp.compartment_index

                pcomp_name = sp_parent.compartment_name
                comp_name = sp.compartment_name

                self.stopwatch("split")
                ub = self.u[comp_name]['u'].split()[submesh_species_index]
                self.stopwatch("split", stop=True)
                self.stopwatch("extrapolate")
                ub.set_allow_extrapolation(True)
                self.stopwatch("extrapolate", stop=True)
                self.stopwatch("Vs")
                Vs = self.V[pcomp_name].sub(parent_species_index)
                self.stopwatch("Vs", stop=True)
                Print('pcomp_name %s, parent_species_index %d' % (pcomp_name, parent_species_index))
                self.stopwatch("interpolate")
                u_dirichlet = d.interpolate(ub, Vs.collapse())
                self.stopwatch("interpolate",stop=True)

                self.stopwatch("DirichletBC")
                bcs.append(d.DirichletBC(Vs, u_dirichlet, self.CD.vmf, sp.compartment.cell_marker))
                self.stopwatch("DirichletBC", stop=True)

                Print("Assigned values from %s (%s) to %s (%s) [DirichletBC]" % (sp_name, comp_name, sp_parent.name, pcomp_name))
        self.bcs=bcs
        return bcs


    def boundary_reactions_forward(self, factor=1, bcs=[]):
        nsubsteps = int(self.config.solver['reaction_substeps'])
        # first reaction step
#        for sp_name, sp in self.SD.Dict.items():
#            if sp.parent_species:
#                comp_name = sp.compartment_name
#                d.solve(self.a[comp_name]==self.L[comp_name], self.u[comp_name]['u'])
#                self.u[comp_name]['n'].assign(self.u[comp_name]['u'])
#                TODO: add picard iterations here?
        for n in range(nsubsteps):
            self.forward_time_step(factor=factor/nsubsteps)
            self.updateTimeDependentParameters()
            for comp_name, comp in self.CD.Dict.items():
                if comp.dimensionality < self.CD.max_dim:
                    if self.config.solver['nonlinear'] == 'picard':
                        self.picard_loop(comp_name, bcs)
                    elif self.config.solver['nonlinear'] == 'newton':
                        self.newton_iter(comp_name)
                    self.u[comp_name]['n'].assign(self.u[comp_name]['u'])


    def boundary_reactions_forward_scipy(self, comp_name, factor=1, all_dofs=False, method='RK45', rtol=1e-4, atol=1e-6):
        self.stopwatch("Boundary reactions forward %s" % comp_name)
        """
        Since FEniCS doesn't support submeshes in parallel we distribute the entire boundary mesh to each CPU
        and parallelize manually
        """

        #TODO: parallelize this

        if all_dofs:
            num_vertices = self.CD.Dict[comp_name].num_vertices
        else:
            x,y,z = (0,0,0) # point to evaluate
            num_vertices = 1
        if comp_name not in self.scipy_odes.keys():
            self.scipy_odes[comp_name] = self.flux_to_scipy(comp_name, mult=num_vertices)
        lode, ptuple, tparam, boundary_species = self.scipy_odes[comp_name]

        nbspecies = len(boundary_species)
        ub = np.full(nbspecies * num_vertices, np.nan)
        for spidx, sp in enumerate(boundary_species):
            pcomp_name = self.SD.Dict[sp].compartment_name
            pcomp_idx = self.SD.Dict[sp].compartment_index
            pcomp_nspecies = self.V['boundary'][pcomp_name][comp_name].num_sub_spaces()
            if pcomp_nspecies==0: pcomp_nspecies=1
            if all_dofs:
                ub[spidx::nbspecies] = self.u[pcomp_name]['b'+comp_name].vector()[pcomp_idx::pcomp_nspecies]
            else:
                ub[spidx] = self.u[pcomp_name]['b'+comp_name](x,y,z)[pcomp_idx]
                

        if all_dofs:
            sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam,ub=ub), [self.t, self.t+self.dt*factor], self.u[comp_name]['n'].vector(), method=method, rtol=rtol, atol=atol)
            # assign solution
            self.u[comp_name]['u'].vector()[:] = sol.y[:,-1]
        else:
            # all vertices have the same value
            sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam,ub=ub), [self.t, self.t+self.dt*factor], self.u[comp_name]['n'](x,y,z), method=method, rtol=rtol, atol=atol)
            for idx, val in enumerate(sol.y[:,-1]):
                stubs.data_manipulation.dolfinSetFunctionValues(self.u[comp_name]['u'], val, idx) 


        self.forward_time_step(factor=factor) # increment time afterwards
        self.u[comp_name]['n'].assign(self.u[comp_name]['u'])

        self.stopwatch("Boundary reactions forward %s" % comp_name, stop=True)



        # if all_dofs:
        #     nspecies = self.CD.Dict[comp_name].num_species
        #     num_vertices = self.CD.Dict[comp_name].num_vertices
        #     mult = int(num_vertices)
        #     if comp_name not in self.scipy_odes.keys():
        #         self.scipy_odes[comp_name] = self.flux_to_scipy(comp_name, mult=mult)
        #     lode, ptuple, tparam, boundary_species = self.scipy_odes[comp_name]

        #     if boundary_species:
        #         nbspecies = len(boundary_species)
        #         ub = np.full(nbspecies * num_vertices, np.nan)
        #         for spidx, sp in enumerate(boundary_species):
        #             pcomp_name = self.SD.Dict[sp].compartment_name
        #             pcomp_idx = self.SD.Dict[sp].compartment_index
        #             pcomp_nspecies = self.V['boundary'][pcomp_name][comp_name].num_sub_spaces()
        #             if pcomp_nspecies==0: pcomp_nspecies=1
        #             ub[spidx::nbspecies] = self.u[pcomp_name]['b'+comp_name].vector()[pcomp_idx::pcomp_nspecies]

        #         sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam,ub=ub), [self.t, self.t+self.dt*factor], self.u[comp_name]['n'].vector(), method='RK45')

        #     # else:
        #         # sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam), [self.t, self.t+self.dt*factor], self.u[comp_name]['n'].vector(), method='RK45')

        #     # assign solution
        #     self.u[comp_name]['u'].vector()[:] = sol.y[:,-1]

        # else:
        #     lode, ptuple, tparam, boundary_species = self.flux_to_scipy(comp_name)
        #     if boundary_species:
        #     sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam,ub=ub), [self.t, self.t+self.dt*factor], self.u[comp_name]['n'](0,0,0), method='BDF')
        #     # else:
        #     #     sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam), [self.t, self.t+self.dt*factor], self.u[comp_name]['n'](0,0,0), method='BDF')
        #     for idx, val in enumerate(sol.y[:,-1]):
        #         stubs.data_manipulation.dolfinSetFunctionValues(self.u[comp_name]['u'], val, self.V[comp_name], idx) 
        

        # self.forward_time_step(factor=factor) # increment time afterwards
        # self.u[comp_name]['n'].assign(self.u[comp_name]['u'])
        # print("finished boundary_reactions_forward_scipy")





# comp_name = 'pm'
# all_dofs = True


# num_vertices = model.CD.Dict[comp_name].num_vertices
# mult = int(num_vertices)
# if comp_name not in model.scipy_odes.keys():
#     model.scipy_odes[comp_name] = model.flux_to_scipy(comp_name, mult=mult)


# lode, ptuple, tparam, boundary_species = model.scipy_odes[comp_name]

# if boundary_species:
#     nbspecies = len(boundary_species)
#     ub = np.full(nbspecies * num_vertices, np.nan)
#     for spidx, sp in enumerate(boundary_species):
#         pcomp_name = model.SD.Dict[sp].compartment_name
#         pcomp_idx = model.SD.Dict[sp].compartment_index
#         pcomp_nspecies = model.V['boundary'][pcomp_name][comp_name].num_sub_spaces()
#         if pcomp_nspecies==0: pcomp_nspecies=1
#         ub[spidx::nbspecies] = model.u[pcomp_name]['b'+comp_name].vector()[pcomp_idx::pcomp_nspecies]

#     sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam,ub=ub), [model.t, model.t+model.dt*factor], model.u[comp_name]['n'].vector(), method='RK45')

# else:
#     sol = solve_ivp(lambda t,y: lode(t,y,ptuple,tparam), [model.t, model.t+model.dt*factor], model.u[comp_name]['n'].vector(), method='RK45')

# # assign solution
# model.u[comp_name]['u'].vector()[:] = sol.y[:,-1]




# model.forward_time_step(factor=factor)
# model.u[comp_name]['n'].assign(model.u[comp_name]['u'])
# print("finished boundary_reactions_forward_scipy")





    def diffusion_forward(self, comp_name, factor=1, bcs=[]):
        self.stopwatch("Diffusion step ["+comp_name+"]")
        self.forward_time_step(factor=factor)
        self.updateTimeDependentParameters()
        if self.config.solver['nonlinear'] == 'picard':
            self.picard_loop(comp_name, bcs)
        elif self.config.solver['nonlinear'] == 'newton':
            self.newton_iter(comp_name)
        self.u[comp_name]['n'].assign(self.u[comp_name]['u'])
        self.stopwatch("Diffusion step ["+comp_name+"]", stop=True)

    def picard_loop(self, comp_name, bcs=[]):
        exit_loop = False
        self.pidx = 0
        while True:
            self.pidx += 1
            if self.CD.Dict[comp_name].dimensionality == self.CD.max_dim:
                linear_solver_settings = self.config.dolfin_linear_coarse
            else:
                linear_solver_settings = self.config.dolfin_linear
            
            d.solve(self.a[comp_name]==self.L[comp_name], self.u[comp_name]['u'], bcs, solver_parameters=linear_solver_settings)
            #print('u (%s) mean: %f' % (comp_name, self.u[comp_name]['u'].compute_vertex_values().mean()))
            self.data.computeError(self.u, comp_name, self.config.solver['norm'])
            self.u[comp_name]['k'].assign(self.u[comp_name]['u'])



            Print('Linf norm (%s) : %f ' % (comp_name, self.data.errors[comp_name]['Linf']['abs'][-1]))
            if self.data.errors[comp_name]['Linf']['abs'][-1] < self.config.solver['linear_abstol']:
                #print("Norm (%f) is less than linear_abstol (%f), exiting picard loop." %
                 #(self.data.errors[comp_name]['Linf'][-1], self.config.solver['linear_abstol']))
                break
#            if self.data.errors[comp_name]['Linf']['rel'][-1] < self.config.solver['linear_reltol']:
#                print("Norm (%f) is less than linear_reltol (%f), exiting picard loop." %
#                (self.data.errors[comp_name]['Linf']['rel'][-1], self.config.solver['linear_reltol']))
#                break

            if self.pidx > self.config.solver['max_picard']:
                Print("Max number of picard iterations reached (%s), exiting picard loop with abs error %f." % 
                (comp_name, self.data.errors[comp_name]['Linf']['abs'][-1]))
                break

    # TODO
    def flux_to_scipy(self, comp_name, mult=1):
        """
        mult allows us to artificially make an ODE repeat e.g. 
        dy = [dy_1, dy_2, dy_3] -> (mult=2) dy=[dy_1, dy_2, dy_3, dy_1, dy_2, dy_3]
        Useful when we want to solve a distributed ODE on some domain so that
        scipy can work its vector optimization magic
        """
        dudt = []
        param_list = []
        time_param_list = []
        species_list = list(self.SD.Dict.values())
        species_list = [s for s in species_list if s.compartment_name==comp_name]
        species_list.sort(key = lambda s: s.compartment_index)
        spname_list = [s.name for s in species_list]
        num_species = len(species_list)

        flux_list = list(self.FD.Dict.values())
        flux_list = [f for f in flux_list if f.species_name in spname_list]

        for idx in range(num_species):
            sp_fluxes = [f.total_scaling*f.signed_stoich*f.symEqn for f in flux_list if f.species_name == spname_list[idx]]
            total_flux = sum(sp_fluxes)
            dudt.append(total_flux)

            if total_flux:
                for psym in total_flux.free_symbols:
                    pname = str(psym)
                    if pname in self.PD.Dict.keys():
                        p = self.PD.Dict[pname]
                        if p.is_time_dependent:
                            time_param_list.append(p)
                        else:
                            param_list.append(pname)

        
        param_list = list(set(param_list))
        time_param_list = list(set(time_param_list))

        ptuple = tuple([self.PD.Dict[str(x)].value for x in param_list])
        time_param_lambda = [lambdify('t', p.symExpr) for p in time_param_list]
        time_param_name_list = [p.name for p in time_param_list]

        free_symbols = list(set([str(x) for total_flux in dudt for x in total_flux.free_symbols]))

        boundary_species = [str(sp) for sp in free_symbols if str(sp) not in spname_list+param_list+time_param_name_list]
        num_boundary_species = len(boundary_species)
        if boundary_species:
            Print("Adding species %s to flux_to_scipy" % boundary_species)
        #Params = namedtuple('Params', param_list)

        dudt_lambda = [lambdify(flatten(spname_list+param_list+time_param_name_list+boundary_species), total_flux) for total_flux in dudt]


        def lambdified_odes(t, u, p, time_p, ub=[]):
            if int(mult*num_species) != len(u):
                raise Exception("mult*num_species [%d x %d = %d] does not match the length of the input vector [%d]!" %
                                (mult, num_species, mult*num_species, len(u)))
            time_p_eval = [f(t) for f in time_p]
            dudt_list = []
            for idx in range(mult):
                idx0 = idx*num_species
                idx0b = idx*num_boundary_species
                inp = flatten([u[idx0 : idx0+num_species], p, time_p_eval, ub[idx0b : idx0b+num_boundary_species]])
                dudt_list.extend([f(*inp) for f in dudt_lambda])
            return dudt_list

        return (lambdified_odes, ptuple, time_param_lambda, boundary_species)

#        # TODO
#        def flux_to_scipy(self, comp_name):
#            dudt = []
#            param_list = []
#            time_param_list = []
#            species_list = list(self.SD.Dict.values())
#            species_list = [s for s in species_list if s.compartment_name==comp_name]
#            species_list.sort(key = lambda s: s.compartment_index)
#            spname_list = [s.name for s in species_list]
#            num_species = len(species_list)
#
#            flux_list = list(self.FD.Dict.values())
#            flux_list = [f for f in flux_list if f.species_name in spname_list]
#
#            for idx in range(num_species):
#                sp_fluxes = [f.total_scaling*f.sign*f.symEqn for f in flux_list if f.species_name == spname_list[idx]]
#                total_flux = sum(sp_fluxes)
#                dudt.append(total_flux)
#
#                if total_flux:
#                    for psym in total_flux.free_symbols:
#                        pname = str(psym)
#                        if pname in self.PD.Dict.keys():
#                            p = self.PD.Dict[pname]
#                            if p.is_time_dependent:
#                                time_param_list.append(p)
#                            else:
#                                param_list.append(pname)
#            
#            param_list = list(set(param_list))
#            time_param_list = list(set(time_param_list))
#
#            ptuple = tuple([self.PD.Dict[str(x)].value for x in param_list])
#            time_param_lambda = [lambdify('t', p.symExpr) for p in time_param_list]
#            time_param_name_list = [p.name for p in time_param_list]
#            #Params = namedtuple('Params', param_list)
#
#            dudt_lambda = [lambdify(flatten(spname_list+param_list+time_param_name_list), total_flux) for total_flux in dudt]
#
#
#            def lambdified_odes(t, u, p, time_p):
#                time_p_eval = [f(t) for f in time_p]
#                inp = flatten([u,p,time_p_eval])
#                return [f(*inp) for f in dudt_lambda]
#
#            return lambdified_odes, ptuple, time_param_lambda













    def newton_iter(self, comp_name):
        #d.solve(self.F[comp_name] == 0, self.u[comp_name]['u'], solver_parameters=self.config.dolfin_linear)
        self.nonlinear_solver[comp_name].solve()


    def sort_forms(self):
        # solve the lower dimensional problem first (usually stiffer)
        comp_list = [self.CD.Dict[key] for key in self.u.keys()]
        self.split_forms = ddict(dict)
        form_types = set([f.form_type for f in self.Forms.form_list])

        if self.config.solver['nonlinear'] == 'picard':
            Print("Splitting problem into bilinear and linear forms for picard iterations: a(u,v) == L(v)")
            for comp in comp_list:
                comp_forms = [f.dolfin_form for f in self.Forms.select_by('compartment_name', comp.name)]
                self.a[comp.name] = d.lhs(sum(comp_forms))
                self.L[comp.name] = d.rhs(sum(comp_forms))
        elif self.config.solver['nonlinear'] == 'newton':
            Print("Formulating problem as F(u;v) == 0 for newton iterations")
            for comp in comp_list:
                comp_forms = [f.dolfin_form for f in self.Forms.select_by('compartment_name', comp.name)]
                #self.F[comp.name] = sum(comp_forms)
                for idx, form in enumerate(comp_forms):
                    J = d.derivative(self.F[comp.name], self.u[comp.name]['u'])
                    problem = d.NonlinearVariationalProblem(self.F[comp.name], self.u[comp.name]['u'], [], J)
                    self.nonlinear_solver[comp.name] = d.NonlinearVariationalSolver(problem)
                    p = self.nonlinear_solver[comp.name].parameters
                    p['newton_solver'].update(self.config.dolfin_linear_coarse)

        elif self.config.solver['nonlinear'] == 'IMEX':
            Print("Keeping forms separated by compartment and form_type for IMEX scheme.")
            for comp in comp_list:
                comp_forms = [f for f in self.Forms.select_by('compartment_name', comp.name)]
                for form_type in form_types:
                    self.split_forms[comp.name][form_type] = sum([f.dolfin_form for f in comp_forms if f.form_type==form_type])

            # 2nd order semi-implicit BDF


#===============================================================================
#===============================================================================
# POST-PROCESSING
#===============================================================================
#===============================================================================
    def init_solver_and_plots(self):
        self.data.initSolutionFiles(self.SD, write_type='xdmf')
        self.data.storeSolutionFiles(self.u, self.t, write_type='xdmf')
        self.data.computeStatistics(self.u, self.t, self.SD)
        self.data.initPlot(self.config)

    def update_solution(self):
        for key in self.u.keys():
            self.u[key]['n'].assign(self.u[key]['u'])
            self.u[key]['k'].assign(self.u[key]['u'])

    def compute_statistics(self):
        self.data.computeStatistics(self.u,self.t,self.SD)
        self.data.outputPickle(self.config)

    def plot_solution(self):
        self.data.storeSolutionFiles(self.u, self.t, write_type='xdmf')
        self.data.plotSolutions(self.config)

#     def init_solver(self):



class FormContainer(object):
    def __init__(self):
        self.form_list = []
    def add(self, new_form):
        self.form_list.append(new_form)
    def select_by(self, selection_key, value):
        return [f for f in self.form_list if getattr(f, selection_key)==value]
    def inspect(self, form_list=None):
        if not form_list:
            form_list = self.form_list

        for index, form in enumerate(form_list):
            Print("Form with index %d from form_list..." % index)
            if form.flux_name:
                Print("Flux name: %s" % form.flux_name)
            Print("Species name: %s" % form.species_name)
            Print("Form type: %s" % form.form_type)
            form.inspect()


class Form(object):
    def __init__(self, dolfin_form, species, form_type, flux_name=None):
        # form_type:
        # 'M': transient/mass form (holds time derivative)
        # 'D': diffusion form
        # 'R': domain reaction forms
        # 'B': boundary reaction forms

        self.dolfin_form = dolfin_form
        self.species = species
        self.species_name = species.name
        self.compartment_name = species.compartment_name
        self.form_type = form_type
        self.flux_name = flux_name

    def inspect(self):
        integrals = self.dolfin_form.integrals()
        for index, integral in enumerate(integrals):
            Print(str(integral) + "\n")
